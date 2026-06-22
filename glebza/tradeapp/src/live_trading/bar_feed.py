"""Live candle stream adapter for portfolio instruments."""

from __future__ import annotations

from typing import Callable, Iterable, Mapping

from exchanges.tinvest_broker import TInvestMarketDataStream, build_instrument_id


def _figi_to_ticker(instruments: Iterable[Mapping[str, object]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in instruments:
        figi = str(item.get("figi") or "").strip()
        ticker = str(item.get("ticker") or "").strip()
        if figi and ticker:
            mapping[figi] = ticker
    return mapping


def _tinvest_id_to_ticker(instruments: Iterable[Mapping[str, object]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in instruments:
        ticker = str(item.get("ticker") or "").strip()
        class_code = str(item.get("class_code") or "").strip()
        if ticker and class_code:
            mapping[build_instrument_id(ticker, class_code)] = ticker
    return mapping


def _attach_ticker(
    bar: dict,
    *,
    figi_to_ticker: dict[str, str],
    tinvest_id_to_ticker: dict[str, str],
) -> dict:
    figi = str(bar.get("figi") or "").strip()
    if figi and figi in figi_to_ticker:
        bar["ticker"] = figi_to_ticker[figi]
        return bar

    tinvest_id = str(bar.get("tinvest_instrument_id") or "").strip()
    if tinvest_id and tinvest_id in tinvest_id_to_ticker:
        bar["ticker"] = tinvest_id_to_ticker[tinvest_id]
    return bar


def stream_daily_closed_candles(
    token: str,
    instruments: Iterable[dict[str, object]],
    on_candle: Callable[[dict], None],
    *,
    target: str | None = None,
) -> None:
    """Subscribe to 1d candles and invoke ``on_candle`` for each completed bar."""
    instrument_rows = list(instruments)
    if not instrument_rows:
        raise ValueError("instruments must not be empty")

    figi_to_ticker = _figi_to_ticker(instrument_rows)
    tinvest_id_to_ticker = _tinvest_id_to_ticker(instrument_rows)
    subscribe_rows = [
        {"ticker": item["ticker"], "class_code": item["class_code"]}
        for item in instrument_rows
    ]

    with TInvestMarketDataStream(token, target=target) as stream:
        stream.subscribe_daily_candles(subscribe_rows, waiting_close=True)
        for bar in stream.iter_closed_candles():
            enriched = _attach_ticker(
                dict(bar),
                figi_to_ticker=figi_to_ticker,
                tinvest_id_to_ticker=tinvest_id_to_ticker,
            )
            on_candle(enriched)
