"""Minimal Carver-style backtest skeleton."""

from __future__ import annotations

from math import sqrt

import pandas as pd

from glebza.tradeapp.src.framework.backtest.result import BacktestResult
from glebza.tradeapp.src.framework.forecasts.combined_forecast import combined_ewmac_forecast_series


def run_single_instrument_backtest(
    klines: pd.DataFrame,
    *,
    periods_per_year: int = 252,
) -> BacktestResult:
    """Backtest one instrument with the current combined EWMAC forecast.

    This is intentionally simple: it uses the combined forecast as exposure,
    ``position = forecast / 10``. Later framework steps will replace this with
    volatility targeting, portfolio weights, costs, and position inertia.
    """

    # Carver stage: instrument universe / portfolio.
    # MVP: this function backtests one instrument only. Later portfolio code will
    # combine multiple instruments with instrument weights and diversification.
    # we alsoo will use the different historical data for different instruments
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
    # TODO: estimate expected price volatility and convert the forecast into a
    # volatility-targeted position.

    # Carver stage: position sizing.
    # MVP placeholder: treat forecast / 10 as direct exposure.
    rows["position"] = rows["combined_forecast"] / 10.0

    # Carver stage: execution, costs, and position inertia.
    # TODO: apply turnover costs, slippage, and no-trade buffers before returns.
    rows["return"] = rows["close_price"].pct_change().fillna(0.0)
    rows["strategy_return"] = (rows["position"].shift(1).fillna(0.0) * rows["return"]).fillna(0.0)

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
