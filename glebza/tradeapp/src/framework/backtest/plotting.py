"""Plotting helpers for backtest results."""

from __future__ import annotations

from pathlib import Path

from glebza.tradeapp.src.framework.backtest.result import BacktestResult


def plot_backtest_metrics(result: BacktestResult, output_path: str | Path) -> Path:
    """Save a chart with total return, close price, forecast, and position size."""

    import matplotlib.pyplot as plt

    rows = result.rows.copy()
    x = rows["k_interval"] if "k_interval" in rows.columns else rows.index
    total_return = rows["equity"] - 1.0

    fig, axes = plt.subplots(nrows=4, ncols=1, figsize=(12, 10), sharex=True)

    axes[0].plot(x, total_return)
    axes[0].set_title("Total Return")
    axes[0].set_ylabel("Return")
    axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0%}"))

    axes[1].plot(x, rows["close_price"])
    axes[1].set_title("Close Price")
    axes[1].set_ylabel("Price")

    axes[2].plot(x, rows["combined_forecast"])
    axes[2].axhline(0.0, color="black", linewidth=0.8)
    axes[2].set_title("Forecast Value")
    axes[2].set_ylabel("Forecast")

    axes[3].plot(x, rows["position"])
    axes[3].axhline(0.0, color="black", linewidth=0.8)
    axes[3].set_title("Position Size")
    axes[3].set_ylabel("Units")
    axes[3].set_xlabel("Time")

    fig.tight_layout()
    fig.autofmt_xdate()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)

    return path
