"""Ingestion gateway module for retrieving market data from MEXC Spot V3."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import orjson
import websockets

LOGGER = logging.getLogger("ingestion_gateway")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)


@dataclass(slots=True)
class WSConfig:
    """Configuration for the :class:`IngestionGateway`."""

    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])
    depth_levels: int = 5
    kline_interval: str = "1m"
    speed: str = "100ms"
    max_retries: int = 5
    ping_interval: float = 15.0
    ping_timeout: float = 10.0

    def _norm_interval(self) -> str:
        iv = self.kline_interval
        if iv.lower().endswith("m") and not iv.startswith("Min"):
            iv = f"Min{iv[:-1]}"
        return iv

    @property
    def depth_streams(self) -> List[str]:
        return [
            f"spot@public.limit.depth.v3.api.pb@{self.speed}@{sym}"
            for sym in self.symbols
        ]

    @property
    def trade_streams(self) -> List[str]:
        return [
            f"spot@public.aggre.deals.v3.api.pb@{self.speed}@{sym}"
            for sym in self.symbols
        ]

    @property
    def kline_streams(self) -> List[str]:
        iv = self._norm_interval()
        return [f"spot@public.kline.v3.api.pb@{sym}@{iv}" for sym in self.symbols]

    @property
    def all_streams(self) -> List[str]:
        return self.depth_streams + self.trade_streams + self.kline_streams


def _to_price_level(raw: List[str]) -> Tuple[float, float]:
    p, q = raw
    return float(p), float(q)


class L2OrderBook:
    """Maintains a level‑2 snapshot for one symbol."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.last_update_id: int | None = None

    def apply_snapshot(self, bids: List[List[str]], asks: List[List[str]], update_id: int):
        self.bids = {p: q for p, q in map(_to_price_level, bids)}
        self.asks = {p: q for p, q in map(_to_price_level, asks)}
        self.last_update_id = update_id

    def apply_delta(self, bids: List[List[str]], asks: List[List[str]], update_id: int):
        if self.last_update_id is None or update_id <= self.last_update_id:
            return
        for p, q in map(_to_price_level, bids):
            if q == 0:
                self.bids.pop(p, None)
            else:
                self.bids[p] = q
        for p, q in map(_to_price_level, asks):
            if q == 0:
                self.asks.pop(p, None)
            else:
                self.asks[p] = q
        self.last_update_id = update_id


class IngestionGateway:
    """WebSocket gateway that connects to the MEXC public feed."""

    BASE_WS = "wss://wbs-api.mexc.com/ws"

    def __init__(self, cfg: WSConfig, event_q: asyncio.Queue[bytes]):
        self.cfg = cfg
        self.q = event_q
        self.orderbooks = {s: L2OrderBook(s) for s in cfg.symbols}
        self._stop = asyncio.Event()

    async def start(self) -> None:
        retries = 0
        while not self._stop.is_set():
            try:
                await self._connect_once()
            except (asyncio.CancelledError, KeyboardInterrupt):
                raise
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("WS error: %s", exc)
                retries += 1
                if retries > self.cfg.max_retries:
                    self._stop.set()
                    break
                await asyncio.sleep(min(2 ** retries, 30))

    async def stop(self) -> None:
        self._stop.set()

    async def _connect_once(self) -> None:
        LOGGER.info("Connecting to %s", self.BASE_WS)
        async with websockets.connect(
            self.BASE_WS,
            ping_interval=self.cfg.ping_interval,
            ping_timeout=self.cfg.ping_timeout,
            max_size=1_000_000,
        ) as ws:
            await self._subscribe(ws)
            async for raw in ws:
                await self._route(json.loads(raw))

    async def _subscribe(self, ws: websockets.WebSocketClientProtocol) -> None:
        sub = {
            "method": "SUBSCRIPTION",
            "params": self.cfg.all_streams,
            "id": 1,
        }
        await ws.send(json.dumps(sub))
        LOGGER.info("Subscribed to %s streams", len(self.cfg.all_streams))

    async def _route(self, msg: Dict[str, Any]) -> None:
        stream = msg.get("p", "")
        if stream.endswith("depth"):
            await self._handle_depth(msg)
        elif stream.endswith("deals"):
            await self._handle_trade(msg)
        elif stream.endswith("kline"):
            await self._handle_kline(msg)
        elif msg.get("code") == 0 and msg.get("msg") == "SUBSCRIPTION":
            LOGGER.info("Subscription confirmed by server")

    async def _handle_depth(self, msg: Dict[str, Any]) -> None:
        d = msg["d"]
        ob = self.orderbooks[d["s"]]
        if d["type"] == "snapshot":
            ob.apply_snapshot(d["bids"], d["asks"], d["u"])
        else:
            ob.apply_delta(d["bids"], d["asks"], d["u"])
        await self._emit({"e": "depth", "s": d["s"], "b": ob.bids, "a": ob.asks, "ts": d["ts"]})

    async def _handle_trade(self, msg: Dict[str, Any]) -> None:
        d = msg["d"]
        await self._emit({"e": "trade", "s": d["s"], "p": d["p"], "q": d["v"], "side": d["T"], "ts": d["ts"]})

    async def _handle_kline(self, msg: Dict[str, Any]) -> None:
        d = msg["d"]
        await self._emit({"e": "kline", "s": d["s"], **d["k"]})

    async def _emit(self, evt: Dict[str, Any]) -> None:
        try:
            self.q.put_nowait(orjson.dumps(evt))
        except asyncio.QueueFull:
            LOGGER.warning("Queue full – event dropped")


async def _printer(q: asyncio.Queue[bytes]) -> None:
    while True:
        evt = orjson.loads(await q.get())
        if evt.get("e") == "kline" and evt["k"]["x"]:
            LOGGER.info("%s close=%.2f vol=%s", evt["s"], float(evt["k"]["c"]), evt["k"]["v"])
        q.task_done()


async def _main() -> None:
    q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=10_000)
    cfg = WSConfig(symbols=["ETHUSDT"], kline_interval="1m", speed="100ms")
    gw = IngestionGateway(cfg, q)
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        def _stop() -> None:
            loop.create_task(gw.stop())
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    await asyncio.gather(gw.start(), _printer(q))


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except RuntimeError as e:  # pragma: no cover - manual execution only
        if "already running" in str(e):
            asyncio.get_event_loop().create_task(_main())
        else:
            raise
