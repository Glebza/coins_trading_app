"""T-Invest API calls used by the daily loader."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from services.tinvest_grpc import TinvestClient
from t_tech.invest import CandleInterval, InstrumentStatus
from t_tech.invest.schemas import Share

_INTERVALS = {
    "1m": CandleInterval.CANDLE_INTERVAL_1_MIN,
    "15m": CandleInterval.CANDLE_INTERVAL_15_MIN,
    "30m": CandleInterval.CANDLE_INTERVAL_30_MIN,
    "4h": CandleInterval.CANDLE_INTERVAL_4_HOUR,
    "1d": CandleInterval.CANDLE_INTERVAL_DAY,
}


def _token() -> str:
    value = os.environ.get("INVEST_TOKEN") or os.environ.get("T_INVEST_TOKEN")
    if not value:
        raise ValueError("INVEST_TOKEN is required")
    return value


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _money(value) -> Decimal:
    units = getattr(value, "units", 0) or 0
    nano = getattr(value, "nano", 0) or 0
    return Decimal(units) + Decimal(nano) / Decimal("1000000000")


def instruments_ticker(share: Share) -> str:
    return share.ticker


class TinvestApi:
    def __init__(self, *, target: Optional[str] = None) -> None:
        self._token = _token()
        self._target = target

    def list_tradeable_shares(
        self,
        *,
        instrument_status: InstrumentStatus = InstrumentStatus.INSTRUMENT_STATUS_BASE,
    ) -> list[Share]:
        rows: list[Share] = []
        with TinvestClient(self._token, target=self._target) as client:
            response = client.instruments.shares(instrument_status=instrument_status)
            for share in response.instruments:
                if not share.buy_available_flag:
                    continue
                if not share.sell_available_flag:
                    continue
                if not share.api_trade_available_flag:
                    continue
                rows.append(share)
        return rows

    def fetch_klines(
        self,
        share: dict,
        interval: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[dict]:
        ticker = share["instruments_ticker"]
        class_code = share["class_code"]
        if interval not in _INTERVALS:
            raise ValueError(f"unsupported interval: {interval}")

        instrument_id = f"{ticker}_{class_code}"
        rows: list[dict] = []
        with TinvestClient(self._token, target=self._target) as client:
            candles: Iterable = client.get_all_candles(
                instrument_id=instrument_id,
                from_=_utc(start_dt),
                to=_utc(end_dt),
                interval=_INTERVALS[interval],
            )
            for candle in candles:
                rows.append(
                    {
                        "k_interval": candle.time,
                        "open_price": _money(candle.open),
                        "high_price": _money(candle.high),
                        "low_price": _money(candle.low),
                        "close_price": _money(candle.close),
                        "volume": int(candle.volume),
                    }
                )
        return rows

    def fetch_dividends(self, share: dict, start_dt: datetime, end_dt: datetime) -> list[dict]:
        ticker = share["instruments_ticker"]
        class_code = share["class_code"]
        instrument_id = f"{ticker}_{class_code}"
        rows: list[dict] = []
        with TinvestClient(self._token, target=self._target) as client:
            dividends = client.instruments.get_dividends(
                instrument_id=instrument_id,
                from_=_utc(start_dt),
                to=_utc(end_dt),
            ).dividends
            for item in dividends:
                dividend_net = getattr(item, "dividend_net", None)
                close_price = getattr(item, "close_price", None)
                yield_value = getattr(item, "yield_value", None)
                rows.append(
                    {
                        "dividend_net": _money(dividend_net),
                        "dividend_currency": getattr(dividend_net, "currency", None) if dividend_net else None,
                        "payment_date": getattr(item, "payment_date", None),
                        "declared_date": getattr(item, "declared_date", None),
                        "last_buy_date": getattr(item, "last_buy_date", None),
                        "dividend_type": getattr(item, "dividend_type", None),
                        "record_date": getattr(item, "record_date", None),
                        "regularity": getattr(item, "regularity", None),
                        "close_price": _money(close_price),
                        "close_price_currency": getattr(close_price, "currency", None) if close_price else None,
                        "yield_value": _money(yield_value),
                        "created_at": getattr(item, "created_at", None),
                    }
                )
        return rows
