"""Environment configuration for transition_service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    backtest_database_url: str
    backtest_schema: str
    live_database_url: str
    live_schema: str


def load_settings() -> Settings:
    backtest_url = os.environ.get("DATABASE_URL", "").strip()
    if not backtest_url:
        raise ValueError("DATABASE_URL is required (backtest database)")

    live_url = os.environ.get("LIVE_DATABASE_URL", "").strip()
    if not live_url:
        raise ValueError("LIVE_DATABASE_URL is required (traderdb / public schema)")

    backtest_schema = os.environ.get("DATABASE_DEFAULT_SCHEMA", "backtests").strip() or "backtests"
    live_schema = os.environ.get("LIVE_DATABASE_DEFAULT_SCHEMA", "public").strip() or "public"

    return Settings(
        backtest_database_url=backtest_url,
        backtest_schema=backtest_schema,
        live_database_url=live_url,
        live_schema=live_schema,
    )
