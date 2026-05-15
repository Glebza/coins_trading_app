"""Backtest result containers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    """Single-instrument backtest output and summary statistics."""

    rows: pd.DataFrame
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    max_drawdown: float
