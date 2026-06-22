"""Run the daily ingestion sequence once."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from daily_loader.settings import Settings, load_settings
from daily_loader.dates import LoadWindows, build_load_windows
from daily_loader.steps import (
    load_dividends_all,
    load_klines_all,
    load_ruonia,
    sync_shares,
    update_volatility,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    windows: LoadWindows
    steps: dict[str, dict] = field(default_factory=dict)


def run_pipeline(*, as_of: Optional[datetime] = None) -> PipelineResult:
    settings = load_settings()
    windows = build_load_windows(
        as_of=as_of,
        kline_lookback_days=settings.kline_lookback_days,
        dividend_lookback_days=settings.dividend_lookback_days,
        ruonia_lookback_days=settings.ruonia_lookback_days,
        vol_lookback_period=settings.vol_lookback_period,
    )
    return _run_steps(windows, settings)


def run_backfill(
    windows: LoadWindows,
    *,
    settings: Optional[Settings] = None,
) -> PipelineResult:
    """One-off historical load for every tradeable share already synced to the DB."""
    effective_settings = settings or load_settings()
    return _run_steps(windows, effective_settings)


def _run_steps(windows: LoadWindows, settings: Settings) -> PipelineResult:
    result = PipelineResult(windows=windows)

    logger.info("step=sync-shares")
    result.steps["sync-shares"] = sync_shares()

    logger.info("step=load-klines-all")
    result.steps["load-klines-all"] = load_klines_all(
        windows,
        interval=settings.kline_interval,
        settings=settings,
    )

    logger.info("step=load-dividends-all")
    result.steps["load-dividends-all"] = load_dividends_all(windows, settings=settings)

    logger.info("step=load-ruonia")
    result.steps["load-ruonia"] = load_ruonia(windows)

    logger.info("step=update-volatility")
    result.steps["update-volatility"] = update_volatility(
        windows,
        interval=settings.kline_interval,
        lookback_period=settings.vol_lookback_period,
    )

    return result
