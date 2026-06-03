"""CLI for running framework backtests against stored market data."""

from __future__ import annotations

import argparse
from datetime import datetime
from math import sqrt
from typing import Optional

import pandas as pd

from framework.backtest import (
    TradingAccount,
    PortfolioBacktestResult,
    run_expanding_oos_portfolio_backtest,
    run_streaming_expanding_oos_portfolio_backtest,
    run_streaming_portfolio_backtest,
    run_weighted_portfolio_backtest,
)
from framework.backtest.plotting import plot_portfolio_backtest_metrics
from framework.instruments.instrument import _parse_dt
from framework.instruments.instruments import InstrumentsService
from framework.portfolio import create_equal_weight_portfolio
from repository.exchange_repository import ExchangeRepository


_PERIODS_PER_YEAR: dict[str, int] = {
    "1m": 252 * 390,
    "15m": 252 * 26,
    "30m": 252 * 13,
    "4h": 252 * 2,
    "1d": 252,
}


def _format_percent(value: float) -> str:
    return f"{value:.2%}"


def _parse_step_months(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("y"):
        years = int(text[:-1])
        return years * 12
    if text.endswith("m"):
        return int(text[:-1])
    raise ValueError("step must use calendar months or years, e.g. 6m or 1y")


def _print_portfolio_summary(
    result: PortfolioBacktestResult,
    *,
    tickers: list[str],
    interval: str,
    account: TradingAccount,
    trailing_stop_multiplier: float,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> None:
    rows = result.rows
    first_interval = rows.index[0]
    last_interval = rows.index[-1]
    last_row = rows.iloc[-1]

    print(f"tickers={','.join(tickers)}")
    print(f"interval={interval}")
    print(f"weights=equal")
    print(f"trading_capital={account.trading_capital:.2f}")
    print(f"annualized_volatility_target={account.annualized_volatility_target:.2%}")
    print(f"commission_rate={account.commission_rate:.4%}")
    print(f"max_capital_multiple={account.max_capital_multiple:.2f}")
    print(f"trailing_stop_multiplier={trailing_stop_multiplier:.2f}")
    print(f"requested_start={start_dt}")
    print(f"requested_end={end_dt}")
    print(f"rows={len(rows)}")
    print(f"first_interval={first_interval}")
    print(f"last_interval={last_interval}")
    print(f"total_return={_format_percent(result.total_return)}")
    print(f"cagr={_format_percent(result.cagr)}")
    print(f"annualized_return={_format_percent(result.annualized_return)}")
    print(f"annualized_volatility={_format_percent(result.annualized_volatility)}")
    print(f"sharpe={result.sharpe:.2f}")
    print(f"max_drawdown={_format_percent(result.max_drawdown)}")
    print(f"last_portfolio_return={_format_percent(last_row['portfolio_return'])}")
    print(f"last_equity={last_row['equity']:.4f}")
    print(f"forecast_diversification_multiplier={result.forecast_diversification_multiplier:.2f}")
    if result.forecast_average_correlation is not None:
        print(f"forecast_average_correlation={result.forecast_average_correlation:.2f}")
    if result.forecast_correlations:
        _print_forecast_correlation_matrix(result.forecast_correlations)
    _print_oos_stage_summaries(rows, interval=interval)


def _print_oos_stage_summaries(rows, *, interval: str) -> None:
    if "oos_stage" not in rows.columns or rows["oos_stage"].dropna().empty:
        return

    periods_per_year = _PERIODS_PER_YEAR[interval]
    print("oos_stage_summaries:")
    print(
        "oos_stage\ttrain_start\ttrain_end\ttest_start\ttest_end\trows\t"
        "total_return\tcagr\tannualized_return\tannualized_volatility\tsharpe\tmax_drawdown"
    )
    for stage, stage_rows in rows.dropna(subset=["oos_stage"]).groupby("oos_stage", sort=True):
        returns = stage_rows["portfolio_return"]
        equity = (1.0 + returns).cumprod()
        drawdown = (equity / equity.cummax()) - 1.0
        return_volatility = float(returns.std(ddof=1))
        if pd.isna(return_volatility):
            return_volatility = 0.0
        annualized_return = float(returns.mean()) * periods_per_year
        annualized_volatility = return_volatility * sqrt(periods_per_year)
        sharpe = annualized_return / annualized_volatility if annualized_volatility else 0.0
        total_return = float(equity.iloc[-1] - 1.0)
        first = stage_rows.iloc[0]
        stage_cagr = _calculate_stage_cagr(stage_rows, total_return)
        print(
            f"{int(stage)}\t"
            f"{first['train_start_dt']}\t"
            f"{first['train_end_dt']}\t"
            f"{first['test_start_dt']}\t"
            f"{first['test_end_dt']}\t"
            f"{len(stage_rows)}\t"
            f"{_format_percent(total_return)}\t"
            f"{_format_percent(stage_cagr)}\t"
            f"{_format_percent(annualized_return)}\t"
            f"{_format_percent(annualized_volatility)}\t"
            f"{sharpe:.2f}\t"
            f"{_format_percent(float(drawdown.min()))}"
        )


def _calculate_stage_cagr(rows, total_return: float) -> float:
    if len(rows.index) < 2:
        return total_return
    dates = pd.to_datetime(rows.index, utc=True)
    elapsed_days = (dates[-1] - dates[0]).total_seconds() / 86_400
    years = elapsed_days / 365.25
    if years <= 0:
        return total_return
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def _print_forecast_correlation_matrix(correlations: dict[str, dict[str, float]]) -> None:
    names = sorted(correlations)
    print("forecast_correlation_matrix:")
    print("forecast_corr\t" + "\t".join(names))
    for row_name in names:
        values = [correlations.get(row_name, {}).get(column_name, 0.0) for column_name in names]
        formatted = "\t".join(f"{value:.2f}" for value in values)
        print(f"forecast_corr\t{row_name}\t{formatted}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the pure framework backtest against klines already stored in PostgreSQL."
    )
    parser.add_argument("--interval", required=True, choices=sorted(_PERIODS_PER_YEAR))
    parser.add_argument(
        "--start-dt",
        required=True,
        help="ISO datetime, e.g. 2023-01-01T00:00:00+00:00.",
    )
    parser.add_argument(
        "--end-dt",
        required=True,
        help="ISO datetime, e.g. 2026-01-01T00:00:00+00:00.",
    )
    parser.add_argument(
        "--periods-per-year",
        type=int,
        default=None,
        help="Override the annualization factor; defaults by interval.",
    )
    parser.add_argument(
        "--trading-capital",
        type=float,
        default=100_000.0,
        help="Cash capital at risk in account currency.",
    )
    parser.add_argument(
        "--annualized-volatility-target",
        type=float,
        default=0.25,
        help="Desired annualized standard deviation, e.g. 0.25 for 25%%.",
    )
    parser.add_argument(
        "--block-value",
        type=float,
        default=1.0,
        help="Currency value of one price point for one instrument unit.",
    )
    parser.add_argument(
        "--position-inertia",
        type=float,
        default=0.10,
        help="No-trade threshold around target position, e.g. 0.10 means 10%%.",
    )
    parser.add_argument(
        "--trailing-stop-multiplier",
        type=float,
        default=4.0,
        help="Trailing stop distance in units of daily price volatility (0 disables). Default 4.",
    )
    parser.add_argument(
        "--plot-path",
        default=None,
        help="Optional PNG path for total return, close price, forecast, and position size chart.",
    )
    parser.add_argument(
        "--strategy-id",
        type=int,
        default=None,
        help="carver_strategy.id (default: first row in backtests.carver_strategy).",
    )
    parser.add_argument(
        "--exchange-code",
        default="tinvest",
        help="exchange.code (brokerage and max_capital_multiple come from the exchange row).",
    )
    parser.add_argument(
        "--volume-percentile",
        type=float,
        default=0.60,
        help="Cross-sectional cutoff for median daily volume (default 0.60 = top 40%%).",
    )
    parser.add_argument(
        "--volatility-percentile",
        type=float,
        default=0.60,
        help="Cross-sectional cutoff for latest stored annualized volatility.",
    )
    parser.add_argument(
        "--include-for-qual-investor",
        action="store_true",
        help="Include shares with for_qual_investor_flag=true (excluded by default).",
    )
    parser.add_argument(
        "--step",
        default=None,
        help=(
            "Enable expanding out-of-sample mode. Use a calendar step like 1y or 6m. "
            "The first step is used for training; each following step is tested with FDM fitted on all past data."
        ),
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help=(
            "Replay backtest: load klines from DB, append one bar at a time to a working dataset, "
            "and use frozen FDM from the training window."
        ),
    )
    parser.add_argument(
        "--training-end-dt",
        default=None,
        help=(
            "Optional ISO datetime end for the FDM training window in streaming mode. "
            "Replay starts at this timestamp; omit to use the full requested window."
        ),
    )
    args = parser.parse_args()

    start_dt = _parse_dt(args.start_dt)
    end_dt = _parse_dt(args.end_dt)
    periods_per_year = args.periods_per_year or _PERIODS_PER_YEAR[args.interval]

    exchange_repo = ExchangeRepository(schema="backtests")
    exchange = exchange_repo.get_exchange_by_code(args.exchange_code)
    if exchange is None:
        raise SystemExit(f"exchange not found in backtests schema: {args.exchange_code}")

    instruments_service = InstrumentsService()
    filtered_shares = instruments_service.filter_shares(
        kline_interval=args.interval,
        volatility_interval=args.interval,
        volume_percentile=args.volume_percentile,
        volatility_percentile=args.volatility_percentile,
        kline_start_dt=start_dt,
        kline_end_dt=end_dt,
        exclude_for_qual_investor=not args.include_for_qual_investor,
    )
    if not filtered_shares:
        raise SystemExit(
            "no shares passed universe filters (liquidity, volatility, kline coverage) — "
            f"load klines for the full window first (interval={args.interval}, "
            f"start_dt={start_dt}, end_dt={end_dt})"
        )

    tickers = [row["instruments_ticker"] for row in filtered_shares]
    print(f"portfolio_universe={len(tickers)} tickers", flush=True)
    print(f"tickers={','.join(tickers)}", flush=True)

    account = TradingAccount(
        trading_capital=args.trading_capital,
        annualized_volatility_target=args.annualized_volatility_target,
        exchange=exchange,
    )

    portfolio = create_equal_weight_portfolio(tickers, block_value=args.block_value)
    training_end_dt = _parse_dt(args.training_end_dt) if args.training_end_dt else None
    try:
        if args.streaming and args.step and training_end_dt is not None:
            raise SystemExit("Use either --step or --training-end-dt, not both")
        if args.streaming and args.step:
            step_months = _parse_step_months(args.step)
            print(f"backtest_mode=streaming_expanding_oos step={args.step}", flush=True)
            result = run_streaming_expanding_oos_portfolio_backtest(
                portfolio,
                account,
                interval=args.interval,
                start_dt=start_dt,
                end_dt=end_dt,
                step_months=step_months,
                periods_per_year=periods_per_year,
                position_inertia=args.position_inertia,
                trailing_stop_multiplier=args.trailing_stop_multiplier,
                strategy_id=args.strategy_id,
                exchange=exchange,
            )
        elif args.streaming:
            print("backtest_mode=streaming_replay", flush=True)
            if training_end_dt is not None:
                print(f"training_end_dt={training_end_dt}", flush=True)
            result = run_streaming_portfolio_backtest(
                portfolio,
                account,
                interval=args.interval,
                start_dt=start_dt,
                end_dt=end_dt,
                training_end_dt=training_end_dt,
                periods_per_year=periods_per_year,
                position_inertia=args.position_inertia,
                trailing_stop_multiplier=args.trailing_stop_multiplier,
                strategy_id=args.strategy_id,
                exchange=exchange,
            )
        elif args.step:
            step_months = _parse_step_months(args.step)
            print(f"backtest_mode=expanding_oos step={args.step}", flush=True)
            result = run_expanding_oos_portfolio_backtest(
                portfolio,
                account,
                interval=args.interval,
                start_dt=start_dt,
                end_dt=end_dt,
                step_months=step_months,
                periods_per_year=periods_per_year,
                position_inertia=args.position_inertia,
                trailing_stop_multiplier=args.trailing_stop_multiplier,
                strategy_id=args.strategy_id,
                exchange=exchange,
            )
        else:
            print("backtest_mode=in_sample", flush=True)
            result = run_weighted_portfolio_backtest(
                portfolio,
                account,
                interval=args.interval,
                start_dt=start_dt,
                end_dt=end_dt,
                periods_per_year=periods_per_year,
                position_inertia=args.position_inertia,
                trailing_stop_multiplier=args.trailing_stop_multiplier,
                strategy_id=args.strategy_id,
                exchange=exchange,
            )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    _print_portfolio_summary(
        result,
        tickers=tickers,
        interval=args.interval,
        account=account,
        trailing_stop_multiplier=args.trailing_stop_multiplier,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    print(f"backtest_run_id={result.run_id}", flush=True)
    if args.plot_path:
        path = plot_portfolio_backtest_metrics(result, args.plot_path)
        print(f"plot_path={path}", flush=True)


if __name__ == "__main__":
    main()
