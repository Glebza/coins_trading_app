"""T-Invest API client for one share: metadata, klines, and dividends."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from typing import Any, Iterable, Optional

from repository.history_repository import HistoryRepository
from t_tech.invest import CandleInterval, Client, InstrumentIdType
from t_tech.invest.schemas import Share
from repository.tinvest_repository import TinvestRepository

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_INTERVALS: dict[str, tuple[CandleInterval, timedelta]] = {
    "1m": (CandleInterval.CANDLE_INTERVAL_1_MIN, timedelta(days=1)),
    "15m": (CandleInterval.CANDLE_INTERVAL_15_MIN, timedelta(days=30)),
    "30m": (CandleInterval.CANDLE_INTERVAL_30_MIN, timedelta(days=60)),
    "4h": (CandleInterval.CANDLE_INTERVAL_4_HOUR, timedelta(days=365)),
    "1d": (CandleInterval.CANDLE_INTERVAL_DAY, timedelta(days=365 * 5)),
}


def _money_to_decimal(value) -> Decimal:
    units = getattr(value, "units", 0) or 0
    nano = getattr(value, "nano", 0) or 0
    return Decimal(units) + (Decimal(nano) / Decimal("1000000000"))


def _money_currency(value) -> Optional[str]:
    return getattr(value, "currency", None) if value is not None else None


def _normalize_dt(dt: Optional[datetime], *, default: Optional[datetime] = None) -> datetime:
    resolved = dt or default
    if resolved is None:
        raise ValueError("datetime value is required")
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc)


def _normalize_from(from_dt: Optional[datetime], interval_key: str) -> datetime:
    if from_dt is not None:
        return _normalize_dt(from_dt)

    try:
        lookback = _INTERVALS[interval_key][1]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported interval '{interval_key}'. Expected one of {sorted(_INTERVALS)}"
        ) from exc
    return datetime.now(timezone.utc) - lookback


class TInvestInstrumentApiService:
    def __init__(self, token: Optional[str] = None, target: Optional[str] = None) -> None:
        self._token = token or os.environ.get("INVEST_TOKEN") or os.environ.get("T_INVEST_TOKEN")
        if not self._token:
            raise ValueError("T-Invest token required: pass token= or set INVEST_TOKEN / T_INVEST_TOKEN")
        self._target = target
        self._history_repo = HistoryRepository()

    def fetch_share(self, figi: str) -> Share:
        """Share metadata from T-Invest (sector, short flag, ticker, class_code, …)."""
        with Client(self._token, target=self._target) as client:
            return client.instruments.share_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
                id=figi,
            ).instrument

    def fetch_dividends_by_share(
        self,
        share: dict,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[dict]:
        """Dividend events for a DB share row."""
        ticker = share["instruments_ticker"]
        class_code = share["class_code"]
        if not ticker or not class_code:
            raise ValueError("Both ticker and class_code are required for T-Invest dividend requests")

        from_utc = _normalize_dt(from_dt)
        to_utc = _normalize_dt(to_dt)
        if to_utc <= from_utc:
            raise ValueError("to_dt must be after from_dt")

        instrument_id = f"{ticker}_{class_code}"
        with Client(self._token, target=self._target) as client:
            response = client.instruments.get_dividends(
                instrument_id=instrument_id,
                from_=from_utc,
                to=to_utc,
            )
        return [self._dividend_to_row(dividend) for dividend in response.dividends]

    def fetch_klines_by_ticker(
        self,
        ticker: str,
        class_code: str,
        interval: str,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> list[dict]:
        """Historical candles for ``{ticker}_{class_code}``."""
        interval_enum, _ = _INTERVALS[interval]
        from_utc = _normalize_from(from_dt, interval)
        to_utc = _normalize_dt(to_dt, default=datetime.now(timezone.utc))

        if not ticker or not class_code:
            raise ValueError("Both ticker and class_code are required for T-Invest candle requests")
        with Client(self._token, target=self._target) as client:
            return self._fetch_candles_with_client(
                client, ticker, class_code, interval_enum, from_utc, to_utc
            )

    def _fetch_candles_with_client(
        self,
        client: Client,
        ticker: str,
        class_code: str,
        interval_enum: CandleInterval,
        from_utc: datetime,
        to_utc: datetime,
    ) -> list[dict]:
        t_invest_instrument_id = f"{ticker}_{class_code}"
        logger.info("t_invest_instrument_id=%s", t_invest_instrument_id)

        rows: list[dict] = []
        candles: Iterable = client.get_all_candles(
            instrument_id=t_invest_instrument_id,
            from_=from_utc,
            to=to_utc,
            interval=interval_enum,
        )
        for candle in candles:
            candle_time = candle.time
            rows.append(
                {
                    "k_interval": candle_time,
                    "open_price": _money_to_decimal(candle.open),
                    "high_price": _money_to_decimal(candle.high),
                    "low_price": _money_to_decimal(candle.low),
                    "close_price": _money_to_decimal(candle.close),
                    "volume": candle.volume,
                }
            )
        return rows

    def _dividend_to_row(self, dividend) -> dict:
        dividend_net = getattr(dividend, "dividend_net", None)
        close_price = getattr(dividend, "close_price", None)
        yield_value = getattr(dividend, "yield_value", None)
        return {
            "dividend_net": _money_to_decimal(dividend_net),
            "dividend_currency": _money_currency(dividend_net),
            "payment_date": getattr(dividend, "payment_date", None),
            "declared_date": getattr(dividend, "declared_date", None),
            "last_buy_date": getattr(dividend, "last_buy_date", None),
            "dividend_type": getattr(dividend, "dividend_type", None),
            "record_date": getattr(dividend, "record_date", None),
            "regularity": getattr(dividend, "regularity", None),
            "close_price": _money_to_decimal(close_price),
            "close_price_currency": _money_currency(close_price),
            "yield_value": _money_to_decimal(yield_value),
            "created_at": getattr(dividend, "created_at", None),
        }

    def sync_share_from_api(
        self,
        figi: str,
        instruments_ticker: str,
        interval: str,
        instrument_repo: TinvestRepository,
        *,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> dict:
        """Fetch share + klines from T-Invest, upsert ``instrument_share``, save klines."""
        api_share = self.fetch_share(figi)
        candles = self.fetch_klines_by_ticker(
            api_share.ticker,
            api_share.class_code,
            interval,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        instrument_id = instrument_repo.upsert_share(
            api_share,
            instruments_ticker=instruments_ticker,
        )
        inserted = self._history_repo.save_tinvest_klines_data(
            instrument_id,
            candles,
            interval,
        )
        logger.info(
            "persisted_share ticker=%s interval=%s klines=%s sector=%s short=%s",
            instruments_ticker,
            interval,
            inserted,
            api_share.sector,
            api_share.short_enabled_flag,
        )
        return {
            "instrument_id": instrument_id,
            "ticker": instruments_ticker,
            "class_code": api_share.class_code,
            "inserted_klines": inserted,
            "sector": api_share.sector,
            "short_enabled_flag": api_share.short_enabled_flag,
        }

def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


