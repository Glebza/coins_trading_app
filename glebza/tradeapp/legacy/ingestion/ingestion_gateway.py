"""ingestion_gateway.py
A minimal but production‑ready **MEXC Spot v3** market‑data ingestion module.

ℹ️  Purpose
───────
* Open resilient WebSocket connections to **kline**, **trades** & **depth** streams.
* Maintain an in‑memory Level‑2 order book (bids/asks up to 5levels).
* Publish cleaned market‑data events to an **asyncio.Queue** so downstream
  modules (Feature Engine, Monitoring, etc.) can consume them.

Written to embed inside a *monolith* yet be trivially extracted into
its own micro‑service later.

Python≥3.10Dependencies:
```
pip install websockets>=12.0 orjson
```

Copyright©2025 – MIT License
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import orjson
import websockets

LOGGER = logging.getLogger("ingestion_gateway")
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass()
class WSConfig:
    """Runtime configuration for the WebSocket client."""

    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])
    depth_levels: int = 5  # 5 | 10 | 20 supported by MEXC
    kline_interval: str = "1m"  # 1m, 5m, etc.

    # Reconnection / heartbeat settings
    max_retries: int = 5
    ping_interval: float = 15.0  # seconds
    ping_timeout: float = 10.0

    # Construct stream names ------------------------------------------------

    @property
    def depth_streams(self) -> List[str]:
        return [
            f"spot@public.limit.depth.v3.api.pb@{sym}@{self.depth_levels}"
            for sym in self.symbols
        ]

    @property
    def trade_streams(self) -> List[str]:
        return [f"spot@public.aggre.deals.v3.api.pb@{sym}" for sym in self.symbols]

    @property
    def kline_streams(self) -> List[str]:
        return [
            f"spot@public.kline.v3.api.pb@{sym}@{self.kline_interval}"
            for sym in self.symbols
        ]

    @property
    def combined_stream(self) -> str:
        """MEXC allows multiple streams over one WS connection, separated by '/'."""

        return "/".join(self.depth_streams + self.trade_streams + self.kline_streams)


# ─────────────────────────────────────────────────────────────────────────────
# Order‑book maintenance helpers
# ─────────────────────────────────────────────────────────────────────────────


def _to_price_level(entry: List[str]) -> Tuple[float, float]:
    price, qty = entry
    return float(price), float(qty)


class L2OrderBook:
    """Maintains a 5/10/20‑level local order‑book snapshot."""
    symbol: str
    bids: Dict[float, float]
    asks: Dict[float, float]
    last_update_id: int | None

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids = {}
        self.asks = {}
        self.last_update_id = None

    # Snapshot / delta application ----------------------------------------

    def apply_snapshot(
        self,
        bids: List[List[str]],
        asks: List[List[str]],
        ts: int,
        update_id: int,
    ) -> None:
        self.bids = {p: q for p, q in map(_to_price_level, bids)}
        self.asks = {p: q for p, q in map(_to_price_level, asks)}
        self.last_update_id = update_id
        LOGGER.debug("%s snapshot applied @%s", self.symbol, ts)

    def apply_delta(
        self,
        bids: List[List[str]],
        asks: List[List[str]],
        update_id: int,
    ) -> None:
        # Ignore out‑of‑order messages.
        if self.last_update_id is None or update_id <= self.last_update_id:
            return

        # Update bids.
        for price, qty in map(_to_price_level, bids):
            if qty == 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = qty

        # Update asks.
        for price, qty in map(_to_price_level, asks):
            if qty == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = qty

        self.last_update_id = update_id

    # Convenience getters --------------------------------------------------

    def best_bid(self) -> Tuple[float, float]:
        if not self.bids:
            return 0.0, 0.0
        price = max(self.bids)
        return price, self.bids[price]

    def best_ask(self) -> Tuple[float, float]:
        if not self.asks:
            return 0.0, 0.0
        price = min(self.asks)
        return price, self.asks[price]

    def spread(self) -> float:
        bid, _ = self.best_bid()
        ask, _ = self.best_ask()
        return ask - bid if ask and bid else float("nan")


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion gateway proper
# ─────────────────────────────────────────────────────────────────────────────


class IngestionGateway:
    """High‑level manager for MEXC SpotV3 WebSocket ingress."""

    BASE_WS = "wss://wbs.mexc.com/raw/ws"

    def __init__(self, cfg: WSConfig, event_queue: asyncio.Queue[bytes]):
        self.cfg = cfg
        self.event_q = event_queue
        self.orderbooks = {sym: L2OrderBook(sym) for sym in cfg.symbols}
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._stop: asyncio.Event = asyncio.Event()

    # Public API -----------------------------------------------------------

    async def start(self) -> None:
        backoff = 1
        attempt = 0
        while not self._stop.is_set():
            try:
                await self._connect_and_run()
            except (asyncio.CancelledError, KeyboardInterrupt):
                raise
            except Exception as exc:  # pylint: disable=broad-except
                attempt += 1
                LOGGER.error(
                    "WS error (%s) – reconnecting in %s (attempt %s/%s)",
                    exc,
                    backoff,
                    attempt,
                    self.cfg.max_retries,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                if attempt >= self.cfg.max_retries:
                    LOGGER.error("Max retries hit – giving up.")
                    self._stop.set()

    async def stop(self) -> None:
        self._stop.set()
        if self._ws:
            await self._ws.close()

    # Internal helpers -----------------------------------------------------

    async def _connect_and_run(self) -> None:
        stream = self.cfg.combined_stream
        url = f"{self.BASE_WS}?streams={stream}"
        LOGGER.info("Connecting to %s", url)
        async with websockets.connect(
            url,
            ping_interval=self.cfg.ping_interval,
            ping_timeout=self.cfg.ping_timeout,
            max_size=1_000_000,
        ) as ws:
            self._ws = ws
            async for raw in ws:
                msg = json.loads(raw)
                await self._handle_msg(msg)

    async def _handle_msg(self, msg: Dict[str, Any]) -> None:
        # Message schema: {"c":"","s":"BTCUSDT","p":"<stream>",...}
        ch = msg.get("p")  # stream name
        if ch is None:
            LOGGER.debug("Unknown message: %s", msg)
            return
        if ch.endswith("depth"):
            await self._handle_depth(msg)
        elif ch.endswith("deals"):
            await self._handle_trade(msg)
        elif ch.endswith("kline"):
            await self._handle_kline(msg)

    # Depth / order‑book ---------------------------------------------------

    async def _handle_depth(self, msg: Dict[str, Any]) -> None:
        data = msg["d"]
        sym = data["s"]
        ob = self.orderbooks[sym]
        if data["type"] == "snapshot":
            ob.apply_snapshot(data["bids"], data["asks"], data["ts"], data["u"])
        else:
            ob.apply_delta(data["bids"], data["asks"], data["u"])

        await self._publish(
            {
                "event": "depth",
                "symbol": sym,
                "book": {
                    "bids": list(ob.bids.items()),
                    "asks": list(ob.asks.items()),
                    "ts": data["ts"],
                },
            }
        )

    # Trades ---------------------------------------------------------------

    async def _handle_trade(self, msg: Dict[str, Any]) -> None:
        data = msg["d"]
        evt = {
            "event": "trade",
            "symbol": data["s"],
            "price": float(data["p"]),
            "qty": float(data["v"]),
            "side": "buy" if data["T"] == 1 else "sell",  # tradeType: 1 buyer is maker
            "ts": data["ts"],
        }
        await self._publish(evt)

    # Klines ---------------------------------------------------------------

    async def _handle_kline(self, msg: Dict[str, Any]) -> None:
        data = msg["d"]
        evt = {
            "event": "kline",
            "symbol": data["s"],
            "interval": data["k"]["t"],
            "open": float(data["k"]["o"]),
            "high": float(data["k"]["h"]),
            "low": float(data["k"]["l"]),
            "close": float(data["k"]["c"]),
            "volume": float(data["k"]["v"]),
            "ts": data["k"]["T"],
        }
        await self._publish(evt)

    # Event dispatch -------------------------------------------------------

    async def _publish(self, event: Dict[str, Any]) -> None:
        """Push an event onto the shared queue using fast orjson serialisation."""

        payload: bytes = orjson.dumps(event)
        try:
            self.event_q.put_nowait(payload)
        except asyncio.QueueFull:
            LOGGER.warning("Event queue full – dropping packet")


# ─────────────────────────────────────────────────────────────────────────────
# Test harness & safe entry‑point
# ─────────────────────────────────────────────────────────────────────────────


async def _consumer(queue: asyncio.Queue[bytes]) -> None:
    """Dummy consumer printing one kline per minute."""

    while True:
        evt = await queue.get()
        parsed = orjson.loads(evt)
        if parsed["event"] == "kline":
            LOGGER.info(
                "%s close=%.2f vol=%.1f", parsed["symbol"], parsed["close"], parsed["volume"]
            )
        queue.task_done()


async def main() -> None:
    cfg = WSConfig(symbols=["BTCUSDT"])
    q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=10000)
    gw = IngestionGateway(cfg,q)
    producer = asyncio.create_task(gw.start())
    consumer = asyncio.create_task(_consumer(q))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda : loop.call_soon(gw._stop.set))
    await asyncio.gather(producer, consumer)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        raise
