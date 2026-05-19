"""CLI for running framework backtests against stored market data."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Optional

from framework.backtest import (
    TradingAccount,
    BacktestResult,
    PortfolioBacktestResult,
    run_single_instrument_backtest,
    run_weighted_portfolio_backtest,
)
from framework.backtest.plotting import plot_backtest_metrics, plot_portfolio_backtest_metrics
from framework.instruments.instrument import _parse_dt
from framework.instruments.instruments import TInvestInstrumentsService
from framework.portfolio import Portfolio, PortfolioInstrument, create_equal_weight_portfolio


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
    account: TradingAccount,
    block_value: float,
    trailing_stop_multiplier: float,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> None:
    rows = result.rows
    first_interval = rows.iloc[0]["k_interval"] if "k_interval" in rows.columns else None
    last_interval = rows.iloc[-1]["k_interval"] if "k_interval" in rows.columns else None
    last_row = rows.iloc[-1]

    print(f"ticker={ticker}")
    print(f"interval={interval}")
    print(f"trading_capital={account.trading_capital:.2f}")
    print(f"annualized_volatility_target={account.annualized_volatility_target:.2%}")
    print(f"commission_rate={account.commission_rate:.4%}")
    print(f"max_capital_multiple={account.max_capital_multiple:.2f}")
    print(f"trailing_stop_multiplier={trailing_stop_multiplier:.2f}")
    print(f"block_value={block_value:.4f}")
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
    print(f"annualized_return={_format_percent(result.annualized_return)}")
    print(f"annualized_volatility={_format_percent(result.annualized_volatility)}")
    print(f"sharpe={result.sharpe:.2f}")
    print(f"max_drawdown={_format_percent(result.max_drawdown)}")
    print(f"last_portfolio_return={_format_percent(last_row['portfolio_return'])}")
    print(f"last_equity={last_row['equity']:.4f}")


def _parse_tickers(value: str) -> list[str]:
    tickers = [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]
    if not tickers:
        raise argparse.ArgumentTypeError("expected at least one ticker")
    if len(tickers) != len(set(tickers)):
        raise argparse.ArgumentTypeError("tickers must be unique")
    return tickers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the pure framework backtest against klines already stored in PostgreSQL."
    )
    ticker_group = parser.add_mutually_exclusive_group(required=True)
    ticker_group.add_argument("--ticker", help="Ticker from instruments.ticker, e.g. SBER.")
    ticker_group.add_argument(
        "--tickers",
        type=_parse_tickers,
        help="Comma-separated tickers for an equal-weight portfolio, e.g. WUSH,UGLD,EUTR,MVID.",
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
        "--lot-size",
        type=int,
        default=None,
        help="Tradable lot size for single-ticker mode. Portfolio mode uses stored instrument lots.",
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
        "--fixed-capital-at-risk",
        action="store_true",
        help="Keep capital at risk fixed at --trading-capital (no compounding with equity).",
    )
    parser.add_argument(
        "--commission-rate",
        type=float,
        default=0.0,
        help="Broker commission as decimal fraction of traded notional, e.g. 0.0005 for 0.05%%.",
    )
    parser.add_argument(
        "--max-capital-multiple",
        type=float,
        default=5.0,
        help="Max abs(position notional) as a multiple of trading capital (per sleeve in portfolio mode).",
    )
    parser.add_argument(
        "--plot-path",
        default=None,
        help="Optional PNG path for total return, close price, forecast, and position size chart.",
    )
    args = parser.parse_args()

    start_dt = _parse_dt(args.start_dt)
    end_dt = _parse_dt(args.end_dt)
    periods_per_year = args.periods_per_year or _PERIODS_PER_YEAR[args.interval]

    service = TInvestInstrumentsService()
    account = TradingAccount(
        trading_capital=args.trading_capital,
        annualized_volatility_target=args.annualized_volatility_target,
        commission_rate=args.commission_rate,
        max_capital_multiple=args.max_capital_multiple,
    )

    if args.ticker:
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

        result = run_single_instrument_backtest(
            klines,
            account=account,
            periods_per_year=periods_per_year,
            block_value=args.block_value,
            lot_size=args.lot_size or 1,
            position_inertia=args.position_inertia,
            trailing_stop_multiplier=args.trailing_stop_multiplier,
            compound_capital_at_risk=not args.fixed_capital_at_risk,
        )
        _print_summary(
            result,
            ticker=args.ticker,
            interval=args.interval,
            account=account,
            block_value=args.block_value,
            trailing_stop_multiplier=args.trailing_stop_multiplier,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        if args.plot_path:
            path = plot_backtest_metrics(result, args.plot_path)
            print(f"plot_path={path}", flush=True)
        return

    base_portfolio = create_equal_weight_portfolio(args.tickers)
    shares_by_ticker = {share["instruments_ticker"]: share for share in service.list_share_rows()}
    portfolio = Portfolio(
        [
            PortfolioInstrument(
                ticker=instrument.ticker,
                weight=instrument.weight,
                block_value=instrument.block_value,
                lot_size=int(shares_by_ticker.get(instrument.ticker, {}).get("lot") or 1),
            )
            for instrument in base_portfolio.instruments
        ]
    )
    instrument_results: dict[str, BacktestResult] = {}
    for instrument in portfolio.instruments:
        klines = service.get_candles_dataframe(
            instrument.ticker,
            args.interval,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=args.limit,
        )
        if klines.empty:
            raise SystemExit(
                f"No stored klines found for ticker='{instrument.ticker}' interval='{args.interval}' "
                f"between {start_dt} and {end_dt}."
            )
        instrument_results[instrument.ticker] = run_single_instrument_backtest(
            klines,
            account=account.allocate_capital(instrument.weight),
            periods_per_year=periods_per_year,
            block_value=instrument.block_value,
            lot_size=instrument.lot_size,
            position_inertia=args.position_inertia,
            trailing_stop_multiplier=args.trailing_stop_multiplier,
            compound_capital_at_risk=not args.fixed_capital_at_risk,
        )

    result = run_weighted_portfolio_backtest(
        instrument_results,
        portfolio,
        periods_per_year=periods_per_year,
    )
    _print_portfolio_summary(
        result,
        tickers=args.tickers,
        interval=args.interval,
        account=account,
        trailing_stop_multiplier=args.trailing_stop_multiplier,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    if args.plot_path:
        path = plot_portfolio_backtest_metrics(result, args.plot_path)
        print(f"plot_path={path}", flush=True)


if __name__ == "__main__":
    main()
