"""One function per daily ingestion step."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal
from math import sqrt
from typing import Optional

from daily_loader.settings import Settings, load_settings
from daily_loader.dates import LoadWindows
from repository.dividend_repository import DividendRepository
from repository.funding_rate_repository import FundingRateRepository
from repository.history_repository import HistoryRepository
from repository.share_repository import ShareRepository
from services.cbr_rates import CbrRatesService
from services.rate_limit import call_with_rate_limit_retries
from services.tinvest_api import TinvestApi, instruments_ticker

logger = logging.getLogger(__name__)

_ANNUALIZATION = {"1d": 252, "4h": 504, "30m": 3276, "15m": 6552, "1m": 98280}


def _settings(settings: Optional[Settings]) -> Settings:
    return settings or load_settings()


def _sleep_between_requests(index: int, total: int, delay_seconds: float) -> None:
    if delay_seconds > 0 and index < total - 1:
        time.sleep(delay_seconds)


def check_tinvest_api() -> dict:
    """Verify gRPC connectivity and token access to T-Invest InstrumentsService."""
    shares = TinvestApi().list_tradeable_shares()
    logger.info("tinvest check ok tradeable_shares=%s", len(shares))
    return {"ok": True, "tradeable_shares": len(shares)}


def sync_shares() -> dict:
    """Refresh metadata for known shares and upsert any new tradeable tickers from T-Invest."""
    api = TinvestApi()
    shares = api.list_tradeable_shares()
    result = ShareRepository().upsert_shares_batch(shares, instruments_ticker_fn=instruments_ticker)
    logger.info(
        "sync-shares fetched=%s new=%s updated=%s listed_in_db=%s",
        result["fetched"],
        result["inserted"],
        result["updated"],
        result["listed_in_db"],
    )
    return result


def load_klines_all(
    windows: LoadWindows,
    *,
    interval: str = "1d",
    settings: Optional[Settings] = None,
) -> dict:
    cfg = _settings(settings)
    shares = ShareRepository().list_shares()
    api = TinvestApi()
    history = HistoryRepository()
    total_inserted = 0
    errors = 0

    for index, share in enumerate(shares):
        ticker = share["instruments_ticker"]
        try:
            candles = call_with_rate_limit_retries(
                lambda: api.fetch_klines(
                    share,
                    interval,
                    windows.kline_start,
                    windows.kline_end,
                ),
                label=f"klines:{ticker}",
                retries=cfg.rate_limit_retries,
                fallback_sleep_seconds=cfg.rate_limit_fallback_sleep_seconds,
            )
            inserted = history.save_klines(int(share["instrument_id"]), candles, interval)
            total_inserted += inserted
            logger.info("klines ticker=%s fetched=%s inserted=%s", ticker, len(candles), inserted)
        except Exception:
            errors += 1
            logger.exception("klines failed ticker=%s", ticker)
        _sleep_between_requests(index, len(shares), cfg.kline_request_delay_seconds)

    return {"shares": len(shares), "inserted": total_inserted, "errors": errors}


def load_dividends_all(
    windows: LoadWindows,
    *,
    settings: Optional[Settings] = None,
) -> dict:
    cfg = _settings(settings)
    shares = ShareRepository().list_shares()
    api = TinvestApi()
    repo = DividendRepository()
    total_stored = 0
    errors = 0

    for index, share in enumerate(shares):
        ticker = share["instruments_ticker"]
        try:
            rows = call_with_rate_limit_retries(
                lambda: api.fetch_dividends(share, windows.dividend_start, windows.dividend_end),
                label=f"dividends:{ticker}",
                retries=cfg.rate_limit_retries,
                fallback_sleep_seconds=cfg.rate_limit_fallback_sleep_seconds,
            )
            stored = repo.upsert_dividends(int(share["instrument_id"]), rows)
            total_stored += stored
            logger.info("dividends ticker=%s fetched=%s stored=%s", ticker, len(rows), stored)
        except Exception:
            errors += 1
            logger.exception("dividends failed ticker=%s", ticker)
        _sleep_between_requests(index, len(shares), cfg.dividend_request_delay_seconds)

    return {"shares": len(shares), "stored": total_stored, "errors": errors}


def load_ruonia(windows: LoadWindows) -> dict:
    rows = CbrRatesService().fetch_ruonia(windows.ruonia_start, windows.ruonia_end)
    stored = FundingRateRepository().upsert_rates(rows)
    logger.info("ruonia fetched=%s stored=%s", len(rows), stored)
    return {"fetched": len(rows), "stored": stored}


def update_volatility(
    windows: LoadWindows,
    *,
    interval: str = "1d",
    lookback_period: int = 252,
) -> dict:
    shares = ShareRepository().list_shares()
    history = HistoryRepository()
    factor = _ANNUALIZATION[interval]
    updated = 0
    errors = 0

    for share in shares:
        ticker = share["instruments_ticker"]
        try:
            rows = history.list_klines(
                int(share["instrument_id"]),
                interval,
                start_dt=windows.vol_start,
                end_dt=windows.vol_end,
            )
            if len(rows) < 2:
                raise ValueError("not enough klines")

            if len(rows) > lookback_period + 1:
                rows = rows[-(lookback_period + 1) :]

            closes = [float(row["close_price"]) for row in rows]
            returns = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes))
                if closes[i - 1] != 0
            ]
            if len(returns) < 2:
                raise ValueError("not enough returns")

            mean = sum(returns) / len(returns)
            variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
            annualized = Decimal(str(sqrt(variance) * sqrt(factor)))

            as_of = rows[-1]["k_interval"]
            if not isinstance(as_of, datetime):
                as_of = datetime.fromisoformat(str(as_of))

            history.save_volatility(
                int(share["instrument_id"]),
                interval,
                as_of,
                lookback_period,
                annualized,
                len(returns),
            )
            updated += 1
            logger.info("volatility ticker=%s as_of=%s value=%s", ticker, as_of, annualized)
        except Exception:
            errors += 1
            logger.exception("volatility failed ticker=%s", ticker)

    return {"shares": len(shares), "updated": updated, "errors": errors}
