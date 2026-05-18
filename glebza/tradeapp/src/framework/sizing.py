"""Position sizing helpers."""

from __future__ import annotations

import pandas as pd

from glebza.tradeapp.src.framework.backtest.account import BacktestAccount
from glebza.tradeapp.src.framework.volatility import daily_cash_volatility_target


def single_instrument_position_size(
    close_price: pd.Series,
    combined_forecast: pd.Series,
    price_volatility: pd.Series,
    account: BacktestAccount,
    *,
    periods_per_year: int = 252,
    block_value: float = 1.0,
) -> pd.Series:
    """Size one instrument from forecast strength and expected price volatility.

    The function first computes the desired percentage of trading capital, then
    converts that capital allocation into instrument units.
    """

    if block_value <= 0:
        raise ValueError("block_value must be positive")

    close = pd.to_numeric(close_price).astype("float64")
    forecast = pd.to_numeric(combined_forecast).astype("float64")
    volatility = pd.to_numeric(price_volatility).astype("float64")

    daily_risk_pct = daily_cash_volatility_target(account, periods_per_year=periods_per_year) / float(
        account.trading_capital
    )
    price_volatility_pct = (volatility / close).where(volatility > 0)
    capital_pct = (forecast / 10.0) * (daily_risk_pct / price_volatility_pct)

    return (float(account.trading_capital) * capital_pct) / (close * block_value)
