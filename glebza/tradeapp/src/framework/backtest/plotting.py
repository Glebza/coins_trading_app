"""Plotting helpers for backtest results."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from glebza.tradeapp.src.framework.backtest.result import BacktestResult, PortfolioBacktestResult


def plot_backtest_metrics(result: BacktestResult, output_path: str | Path) -> Path:
    """Save a chart with total return, close price, forecast, and position size."""

    import matplotlib.pyplot as plt

    rows = result.rows.copy()
    x = rows["k_interval"] if "k_interval" in rows.columns else rows.index
    total_return = rows["equity"] - 1.0

    fig, axes = plt.subplots(nrows=5, ncols=1, figsize=(12, 12), sharex=True)

    axes[0].plot(x, total_return)
    axes[0].set_title("Total Return")
    axes[0].set_ylabel("Return")
    axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))

    axes[1].plot(x, rows["equity"])
    axes[1].axhline(1.0, color="black", linewidth=0.8)
    axes[1].set_title("Equity")
    axes[1].set_ylabel("Equity")

    axes[2].plot(x, rows["close_price"])
    axes[2].set_title("Close Price")
    axes[2].set_ylabel("Price")

    forecast_columns = sorted(column for column in rows.columns if column.startswith("forecast_"))
    for column in forecast_columns:
        axes[3].plot(x, rows[column], label=column.removeprefix("forecast_"), alpha=0.7, linewidth=1.0)
    axes[3].plot(x, rows["combined_forecast"], label="combined", color="black", linewidth=2.0)
    axes[3].axhline(0.0, color="black", linewidth=0.8)
    axes[3].set_title("Forecasts")
    axes[3].set_ylabel("Forecast")
    if forecast_columns:
        axes[3].legend(loc="best", fontsize=8)

    axes[4].plot(x, rows["position"])
    axes[4].axhline(0.0, color="black", linewidth=0.8)
    axes[4].set_title("Position Size")
    axes[4].set_ylabel("Units")
    axes[4].set_xlabel("Time")

    fig.tight_layout()
    fig.autofmt_xdate()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)

    return path


def _instrument_rows_indexed(inst_rows: pd.DataFrame) -> pd.DataFrame:
    if "k_interval" in inst_rows.columns:
        return inst_rows.set_index("k_interval")
    return inst_rows


def plot_portfolio_backtest_metrics(result: PortfolioBacktestResult, output_path: str | Path) -> Path:
    """Save portfolio return, equity, notional, and return contributions per instrument."""

    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    rows = result.rows.copy()
    x = rows.index
    total_return = rows["equity"] - 1.0
    weighted_return_columns = [column for column in rows.columns if column.endswith("_weighted_return")]

    fig, axes = plt.subplots(nrows=4, ncols=1, figsize=(12, 12), sharex=True)

    axes[0].plot(x, total_return)
    axes[0].set_title("Portfolio Total Return")
    axes[0].set_ylabel("Return")
    axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))

    axes[1].plot(x, rows["equity"])
    axes[1].axhline(1.0, color="black", linewidth=0.8)
    axes[1].set_title("Portfolio Equity")
    axes[1].set_ylabel("Equity")

    for ticker, instrument_result in sorted(result.instrument_results.items()):
        indexed = _instrument_rows_indexed(instrument_result.rows)
        position = indexed["position"].reindex(x).fillna(0.0)
        notional = (position * indexed["close_price"].reindex(x)).fillna(0.0)
        axes[2].plot(x, notional, label=ticker)
    axes[2].axhline(0.0, color="black", linewidth=0.8)
    axes[2].set_title("Position Notional (Shares × Close)")
    axes[2].set_ylabel("Notional")
    axes[2].legend(loc="best", fontsize=8)

    for column in weighted_return_columns:
        ticker = column.removesuffix("_weighted_return")
        contribution = (1.0 + rows[column]).cumprod() - 1.0
        axes[3].plot(x, contribution, label=ticker)
    axes[3].set_title("Weighted Instrument Return Contributions")
    axes[3].set_ylabel("Contribution")
    axes[3].set_xlabel("Time")
    axes[3].yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))
    if weighted_return_columns:
        axes[3].legend(loc="best", fontsize=8)

    for axis in axes:
        axis.set_xlim(x[0], x[-1])
        if pd.api.types.is_datetime64_any_dtype(x):
            locator = mdates.AutoDateLocator(minticks=10, maxticks=24)
            axis.xaxis.set_major_locator(locator)
            axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        else:
            axis.xaxis.set_major_locator(MaxNLocator(nbins=16, integer=True))
    fig.tight_layout()
    fig.autofmt_xdate(rotation=30, ha="right")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)

    return path
