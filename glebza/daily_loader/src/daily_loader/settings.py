"""Environment-backed settings for the daily_loader pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    kline_interval: str
    kline_lookback_days: int
    dividend_lookback_days: int
    ruonia_lookback_days: int
    vol_lookback_period: int
    kline_request_delay_seconds: float
    dividend_request_delay_seconds: float
    rate_limit_retries: int
    rate_limit_fallback_sleep_seconds: float


def load_settings() -> Settings:
    return Settings(
        kline_interval=os.environ.get("DAILY_LOADER_KLINE_INTERVAL", "1d").strip() or "1d",
        kline_lookback_days=_int("DAILY_LOADER_KLINE_LOOKBACK_DAYS", 1),
        dividend_lookback_days=_int("DAILY_LOADER_DIVIDEND_LOOKBACK_DAYS", 365),
        ruonia_lookback_days=_int("DAILY_LOADER_RUONIA_LOOKBACK_DAYS", 30),
        vol_lookback_period=_int("DAILY_LOADER_VOL_LOOKBACK_PERIOD", 252),
        kline_request_delay_seconds=_float("DAILY_LOADER_KLINE_REQUEST_DELAY_SECONDS", 0.3),
        dividend_request_delay_seconds=_float("DAILY_LOADER_DIVIDEND_REQUEST_DELAY_SECONDS", 0.5),
        rate_limit_retries=_int("DAILY_LOADER_RATE_LIMIT_RETRIES", 3),
        rate_limit_fallback_sleep_seconds=_float("DAILY_LOADER_RATE_LIMIT_FALLBACK_SLEEP_SECONDS", 60.0),
    )
