"""Backtest result containers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    """Single-instrument backtest output and summary statistics."""

    rows: pd.DataFrame
    total_return: float
    cagr: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    max_drawdown: float
    periods_per_year: int = 252
    forecast_diversification_multiplier: float = 1.0
    forecast_average_correlation: Optional[float] = None
    forecast_correlations: Optional[dict[str, dict[str, float]]] = None


@dataclass(frozen=True)
class PortfolioBacktestResult:
    """Aggregated portfolio backtest output and summary statistics."""

    rows: pd.DataFrame
    instrument_results: dict[str, BacktestResult]
    total_return: float
    cagr: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    max_drawdown: float
    run_id: int | None = None
    periods_per_year: int = 252
    forecast_diversification_multiplier: float = 1.0
    forecast_average_correlation: Optional[float] = None
    forecast_correlations: Optional[dict[str, dict[str, float]]] = None
