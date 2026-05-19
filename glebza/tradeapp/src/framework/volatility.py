"""Volatility targeting helpers for Carver-style position sizing."""

from __future__ import annotations

from math import sqrt

import pandas as pd

from glebza.tradeapp.src.framework.account import TradingAccount


def annual_cash_volatility_target(account: TradingAccount) -> float:
    """Annual expected cash standard deviation of portfolio returns."""
    return float(account.trading_capital) * account.annualized_volatility_target


def daily_cash_volatility_target(account: TradingAccount, *, periods_per_year: int = 252) -> float:
    """Daily cash volatility target, annual target divided by square root of time."""
    return annual_cash_volatility_target(account) / sqrt(periods_per_year)


def estimate_daily_price_volatility(
    close_price: pd.Series,
    *,
    span: int = 32,
    min_periods: int = 2,
) -> pd.Series:
    """Estimate expected daily price volatility  in price_points from absolute price changes."""
    close = pd.to_numeric(close_price).astype("float64")
    price_changes = close.diff()
    volatility = price_changes.ewm(span=span, min_periods=min_periods).std()
    return volatility


