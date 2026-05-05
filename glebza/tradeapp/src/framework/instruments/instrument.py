"""T-Invest candle loading helpers for share instruments."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional

from repository.history_repository import HistoryRepository
from t_tech.invest import CandleInterval, Client
from t_tech.invest.schemas import Share

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_INTERVALS: dict[str, tuple[CandleInterval, timedelta]] = {
    "1m": (CandleInterval.CANDLE_INTERVAL_1_MIN, timedelta(days=1)),
    "15m": (CandleInterval.CANDLE_INTERVAL_15_MIN, timedelta(days=30)),
    "30m": (CandleInterval.CANDLE_INTERVAL_30_MIN, timedelta(days=60)),
    "4h": (CandleInterval.CANDLE_INTERVAL_4_HOUR, timedelta(days=365)),
    "1d": (CandleInterval.CANDLE_INTERVAL_DAY, timedelta(days=365 * 5)),
}


def share_sector(share: Share, *, max_len: int = 256) -> Optional[str]:
    """T-Invest Share.sector (сектор экономики), normalized for DB storage."""
    v = getattr(share, "sector", None)
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s if len(s) <= max_len else s[:max_len]


def _money_to_decimal(value) -> Decimal:
    units = getattr(value, "units", 0) or 0
    nano = getattr(value, "nano", 0) or 0
    return Decimal(units) + (Decimal(nano) / Decimal("1000000000"))


def _normalize_from(from_dt: Optional[datetime], interval_key: str) -> datetime:
    if from_dt is not None:
        if from_dt.tzinfo is None:
            return from_dt.replace(tzinfo=timezone.utc)
        return from_dt.astimezone(timezone.utc)

    try:
        lookback = _INTERVALS[interval_key][1]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported interval '{interval_key}'. Expected one of {sorted(_INTERVALS)}"
        ) from exc
    return datetime.now(timezone.utc) - lookback


class TInvestKlineService:
    def __init__(self, token: Optional[str] = None, target: Optional[str] = None) -> None:
        self._token = token or os.environ.get("INVEST_TOKEN") or os.environ.get("T_INVEST_TOKEN")
        if not self._token:
            raise ValueError("T-Invest token required: pass token= or set INVEST_TOKEN / T_INVEST_TOKEN")
        self._target = target
        self._history_repo = HistoryRepository()

    def fetch_candles(
        self,
        ticker: str,
        class_code: str,
        interval: str,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> list[dict]:
        interval_enum, _ = _INTERVALS[interval]
        from_utc = _normalize_from(from_dt, interval)
        to_utc = (to_dt or datetime.now(timezone.utc))
        if to_utc.tzinfo is None:
            to_utc = to_utc.replace(tzinfo=timezone.utc)
        else:
            to_utc = to_utc.astimezone(timezone.utc)

        if not ticker or not class_code:
            raise ValueError("Both ticker and class_code are required for T-Invest candle requests")
        t_invest_instrument_id = f"{ticker}_{class_code}"
        logger.info("t_invest_instrument_id=%s", t_invest_instrument_id)

        rows: list[dict] = []
        with Client(self._token, target=self._target) as client:
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

    def persist_candles(
        self,
        db_instrument_id: int,
        ticker: str,
        class_code: str,
        interval: str,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> int:
        candles = self.fetch_candles(ticker, class_code, interval, from_dt=from_dt, to_dt=to_dt)
        inserted = self._history_repo.save_tinvest_klines_data(
            db_instrument_id,
            candles,
            interval,
        )
        logger.info("persisted_klines=%s ticker=%s interval=%s", inserted, ticker, interval)
        return inserted


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch T-Invest candles and store them in PostgreSQL")
    parser.add_argument("--db-instrument-id", required=True, type=int, help="DB instruments.id value")
    parser.add_argument("--ticker", required=True, help="Ticker from instruments.ticker / instrument_share.ticker")
    parser.add_argument("--class-code", required=True, help="T-Invest class_code from instrument_share")
    parser.add_argument("--interval", required=True, choices=sorted(_INTERVALS), help="Kline table interval")
    parser.add_argument("--from-dt", dest="from_dt", help="ISO datetime, default depends on interval")
    parser.add_argument("--to-dt", dest="to_dt", help="ISO datetime, default: now UTC")
    args = parser.parse_args()

    svc = TInvestKlineService()
    inserted = svc.persist_candles(
        args.db_instrument_id,
        args.ticker,
        args.class_code,
        args.interval,
        from_dt=_parse_dt(args.from_dt),
        to_dt=_parse_dt(args.to_dt),
    )
    print(f"persisted_klines={inserted}", flush=True)


if __name__ == "__main__":
    main()
