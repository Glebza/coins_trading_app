"""CLI for running framework backtests against stored market data."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Optional

from framework.backtest import BacktestResult, run_single_instrument_backtest
from framework.instruments.instrument import _parse_dt
from framework.instruments.instruments import TInvestInstrumentsService


_PERIODS_PER_YEAR: dict[str, int] = {
    "1m": 252 * 390,
    "15m": 252 * 26,
    "30m": 252 * 13,
    "4h": 252 * 2,
    "1d": 252,
}


def _format_percent(value: float) -> str:
    return f"{value:.2%}"


def _print_summary(
    result: BacktestResult,
    *,
    ticker: str,
    interval: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> None:
    rows = result.rows
    first_interval = rows.iloc[0]["k_interval"] if "k_interval" in rows.columns else None
    last_interval = rows.iloc[-1]["k_interval"] if "k_interval" in rows.columns else None
    last_row = rows.iloc[-1]

    print(f"ticker={ticker}")
    print(f"interval={interval}")
    print(f"requested_start={start_dt}")
    print(f"requested_end={end_dt}")
    print(f"rows={len(rows)}")
    print(f"first_interval={first_interval}")
    print(f"last_interval={last_interval}")
    print(f"total_return={_format_percent(result.total_return)}")
    print(f"annualized_return={_format_percent(result.annualized_return)}")
    print(f"annualized_volatility={_format_percent(result.annualized_volatility)}")
    print(f"sharpe={result.sharpe:.2f}")
    print(f"max_drawdown={_format_percent(result.max_drawdown)}")
    print(f"last_close={last_row['close_price']:.4f}")
    print(f"last_forecast={last_row['combined_forecast']:.2f}")
    print(f"last_position={last_row['position']:.2f}")
    print(f"last_equity={last_row['equity']:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the pure framework backtest against klines already stored in PostgreSQL."
    )
    parser.add_argument("--ticker", required=True, help="Ticker from instruments.ticker, e.g. SBER.")
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
        "--limit",
        type=int,
        default=None,
        help="Optional max number of stored kline rows to read.",
    )
    parser.add_argument(
        "--periods-per-year",
        type=int,
        default=None,
        help="Override the annualization factor; defaults by interval.",
    )
    args = parser.parse_args()

    start_dt = _parse_dt(args.start_dt)
    end_dt = _parse_dt(args.end_dt)
    periods_per_year = args.periods_per_year or _PERIODS_PER_YEAR[args.interval]

    service = TInvestInstrumentsService()
    klines = service.get_candles_dataframe(
        args.ticker,
        args.interval,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=args.limit,
    )
    if klines.empty:
        raise SystemExit(
            f"No stored klines found for ticker='{args.ticker}' interval='{args.interval}' "
            f"between {start_dt} and {end_dt}."
        )

    result = run_single_instrument_backtest(klines, periods_per_year=periods_per_year)
    _print_summary(
        result,
        ticker=args.ticker,
        interval=args.interval,
        start_dt=start_dt,
        end_dt=end_dt,
    )


if __name__ == "__main__":
    main()
