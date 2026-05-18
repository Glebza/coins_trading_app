"""Portfolio backtest aggregation helpers."""

from __future__ import annotations

from math import sqrt
from typing import Mapping

import pandas as pd

from glebza.tradeapp.src.framework.backtest.result import BacktestResult, PortfolioBacktestResult
from glebza.tradeapp.src.framework.portfolio import Portfolio


def run_weighted_portfolio_backtest(
    instrument_results: Mapping[str, BacktestResult],
    portfolio: Portfolio,
    *,
    periods_per_year: int = 252,
) -> PortfolioBacktestResult:
    """Run a fixed-weight portfolio backtest from single-instrument backtests.

    Each instrument result is aligned by ``k_interval`` when available, otherwise
    by row index. The first version uses an inner join so every portfolio return
    is based on instruments that all have data for that timestamp.
    """

    missing = [instrument.ticker for instrument in portfolio.instruments if instrument.ticker not in instrument_results]
    if missing:
        raise ValueError(f"missing backtest results for tickers: {missing}")

    return_columns: list[pd.Series] = []
    for instrument in portfolio.instruments:
        rows = instrument_results[instrument.ticker].rows
        if "strategy_return" not in rows.columns:
            raise ValueError(f"strategy_return column is missing for ticker '{instrument.ticker}'")

        if "k_interval" in rows.columns:
            series = rows.set_index("k_interval")["strategy_return"]
        else:
            series = rows["strategy_return"]
        return_columns.append(pd.to_numeric(series).rename(instrument.ticker))

    returns = pd.concat(return_columns, axis=1, join="inner").sort_index()
    if returns.empty:
        raise ValueError("no overlapping return rows for portfolio instruments")

    result_rows = returns.copy()
    for instrument in portfolio.instruments:
        result_rows[f"{instrument.ticker}_weighted_return"] = result_rows[instrument.ticker] * instrument.weight

    weighted_columns = [f"{instrument.ticker}_weighted_return" for instrument in portfolio.instruments]
    result_rows["portfolio_return"] = result_rows[weighted_columns].sum(axis=1)
    result_rows["equity"] = (1.0 + result_rows["portfolio_return"]).cumprod()
    result_rows["drawdown"] = (result_rows["equity"] / result_rows["equity"].cummax()) - 1.0

    total_return = float(result_rows["equity"].iloc[-1] - 1.0)
    mean_return = float(result_rows["portfolio_return"].mean())
    return_volatility = float(result_rows["portfolio_return"].std(ddof=1))
    if pd.isna(return_volatility):
        return_volatility = 0.0

    annualized_return = mean_return * periods_per_year
    annualized_volatility = return_volatility * sqrt(periods_per_year)
    sharpe = annualized_return / annualized_volatility if annualized_volatility else 0.0
    max_drawdown = float(result_rows["drawdown"].min())

    return PortfolioBacktestResult(
        rows=result_rows,
        instrument_results={instrument.ticker: instrument_results[instrument.ticker] for instrument in portfolio.instruments},
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
    )
