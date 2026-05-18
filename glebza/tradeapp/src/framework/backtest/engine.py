"""Minimal Carver-style backtest skeleton."""

from __future__ import annotations

from math import sqrt

import pandas as pd

from glebza.tradeapp.src.framework.backtest.account import BacktestAccount
from glebza.tradeapp.src.framework.backtest.result import BacktestResult
from glebza.tradeapp.src.framework.forecasts.combined_forecast import combined_ewmac_forecast_series
from glebza.tradeapp.src.framework.sizing import single_instrument_position_size
from glebza.tradeapp.src.framework.volatility import (
    estimate_daily_price_volatility,
)


def run_single_instrument_backtest(
    klines: pd.DataFrame,
    *,
    account: BacktestAccount | None = None,
    periods_per_year: int = 252,
    block_value: float = 1.0,
) -> BacktestResult:
    """Backtest one instrument with the current combined EWMAC forecast.

    This is intentionally simple: it converts the combined forecast into a
    volatility-targeted position. Later framework steps will add portfolio
    weights, costs, and position inertia.
    """
    if account is None:
        account = BacktestAccount(trading_capital=100_000.0, annualized_volatility_target=0.35)

    # Carver stage: instrument universe / portfolio.
    # MVP: this function backtests one instrument only. Later portfolio code will
    # combine multiple instruments with instrument weights and diversification.
    # Later, each instrument can also use its own historical data window.
    rows = klines.copy()
    if "k_interval" in rows.columns:
        rows = rows.sort_values("k_interval").reset_index(drop=True)

    # Carver stage: market data preparation.
    # MVP: use close-to-close returns from stored klines.
    rows["close_price"] = pd.to_numeric(rows["close_price"]).astype("float64")

    # Carver stage: applicable trading rules and forecast combination.
    # MVP: use the default combined EWMAC forecast.
    rows["combined_forecast"] = combined_ewmac_forecast_series(rows)

    # Carver stage: expected volatility and risk target.
    rows["price_volatility"] = estimate_daily_price_volatility(rows["close_price"])

    # Carver stage: position sizing.
    rows["position"] = single_instrument_position_size(
        rows["close_price"],
        rows["combined_forecast"],
        rows["price_volatility"],
        account,
        periods_per_year=periods_per_year,
        block_value=block_value,
    ).fillna(0.0)

    # Carver stage: execution, costs, and position inertia.
    # TODO: apply slippage and no-trade buffers before returns.
    rows["return"] = rows["close_price"].pct_change().fillna(0.0)
    rows["price_change"] = rows["close_price"].diff().fillna(0.0)
    rows["turnover"] = rows["position"].diff().abs().fillna(rows["position"].abs())
    rows["commission"] = rows["turnover"] * rows["close_price"] * block_value * account.commission_rate
    rows["gross_strategy_return"] = (
        rows["position"].shift(1).fillna(0.0) * rows["price_change"] * block_value / float(account.trading_capital)
    ).fillna(0.0)
    rows["commission_return"] = rows["commission"] / float(account.trading_capital)
    rows["strategy_return"] = rows["gross_strategy_return"] - rows["commission_return"]

    # Carver stage: account curve and risk reporting.
    rows["equity"] = (1.0 + rows["strategy_return"]).cumprod()
    rows["drawdown"] = (rows["equity"] / rows["equity"].cummax()) - 1.0

    total_return = float(rows["equity"].iloc[-1] - 1.0)
    mean_return = float(rows["strategy_return"].mean())
    return_volatility = float(rows["strategy_return"].std(ddof=1))
    annualized_return = mean_return * periods_per_year
    annualized_volatility = return_volatility * sqrt(periods_per_year)
    sharpe = annualized_return / annualized_volatility if annualized_volatility else 0.0
    max_drawdown = float(rows["drawdown"].min())

    return BacktestResult(
        rows=rows,
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
    )
