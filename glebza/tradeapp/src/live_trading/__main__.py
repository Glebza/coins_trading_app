"""Live trading CLI: broker connectivity smoke tests (POC-1/2)."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from live_trading.bar_feed import stream_daily_closed_candles
from live_trading.deployment_config import (
    load_deployment,
    resolve_backtest_run_id,
    resolve_exchange_code,
    resolve_strategy_id,
)
from exchanges.tinvest_broker import TInvestBrokerClient
from live_trading.tinvest_session import TinvestSession

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(levelname)s: %(asctime)s %(message)s",
        level=logging.INFO,
    )


def _add_strategy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--strategy-id",
        type=int,
        default=None,
        help="carver_strategy.id (or LIVE_STRATEGY_ID env).",
    )
    parser.add_argument(
        "--backtest-run-id",
        type=int,
        default=None,
        help="Frozen FDM source run (or LIVE_BACKTEST_RUN_ID env).",
    )
    parser.add_argument(
        "--trading-capital",
        type=float,
        default=None,
        help="Override carver_strategy.initial_trading_capital for sizing.",
    )
    parser.add_argument(
        "--exchange-code",
        default=None,
        help="Broker exchange code (default: tinvest or LIVE_EXCHANGE_CODE env).",
    )


def _load_deployment(args: argparse.Namespace):
    strategy_id = resolve_strategy_id(args.strategy_id)
    backtest_run_id = resolve_backtest_run_id(args.backtest_run_id)
    return load_deployment(
        strategy_id,
        backtest_run_id=backtest_run_id,
        exchange_code=resolve_exchange_code(args.exchange_code),
        trading_capital=args.trading_capital,
    )


def _stream_instruments_payload(deployment) -> list[dict[str, object]]:
    return [
        {
            "ticker": item.ticker,
            "class_code": item.class_code,
            "figi": item.figi,
            "instrument_id": item.instrument_id,
            "short_enabled_flag": item.short_enabled,
            "lot_size": item.lot_size,
        }
        for item in deployment.stream_instruments
    ]


def _cmd_list_accounts(_: argparse.Namespace) -> None:
    session = TinvestSession.from_env()
    broker = TInvestBrokerClient(
        session.token,
        session.account_id,
        sandbox=session.sandbox,
        target=session.target,
    )
    accounts = broker.list_accounts()
    print(f"sandbox={session.sandbox}")
    print(f"resolved_account_id={session.account_id}")
    print(json.dumps(accounts, ensure_ascii=False, indent=2))


def _cmd_connect(_: argparse.Namespace) -> None:
    session = TinvestSession.from_env()
    broker = TInvestBrokerClient(
        session.token,
        session.account_id,
        sandbox=session.sandbox,
        target=session.target,
    )
    accounts = broker.list_accounts()
    portfolio = broker.get_portfolio()
    positions = broker.get_positions()
    print(f"sandbox={session.sandbox}")
    print(f"account_id={session.account_id}")
    print(f"accounts={json.dumps(accounts, ensure_ascii=False)}")
    print(f"portfolio={json.dumps(portfolio, ensure_ascii=False, default=str)}")
    print(f"positions={json.dumps(positions, ensure_ascii=False, default=str)}")


def _cmd_stream_test(args: argparse.Namespace) -> None:
    session = TinvestSession.from_env()
    deployment = _load_deployment(args)
    instruments = _stream_instruments_payload(deployment)
    tickers = [item["ticker"] for item in instruments]
    print(
        f"strategy_id={deployment.strategy_id} portfolio_id={deployment.portfolio_id} "
        f"backtest_run_id={deployment.backtest_run_id} fdm={deployment.fdm_multiplier:.4f} "
        f"tickers={','.join(tickers)} count={len(instruments)}",
        flush=True,
    )

    seen = 0

    def on_candle(bar: dict) -> None:
        nonlocal seen
        seen += 1
        print(json.dumps(bar, ensure_ascii=False, default=str), flush=True)
        if args.max_candles and seen >= args.max_candles:
            raise SystemExit(0)

    stream_daily_closed_candles(
        session.token,
        instruments,
        on_candle,
        target=session.target,
    )


def main() -> None:
    _configure_logging()
    parser = argparse.ArgumentParser(
        description="T-Invest broker connectivity smoke tests.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_accounts = sub.add_parser(
        "list-accounts",
        help="List accounts and show auto-resolved latest open sandbox account id.",
    )
    p_accounts.set_defaults(handler=_cmd_list_accounts)

    p_connect = sub.add_parser("connect", help="Verify token, account, portfolio, and positions.")
    p_connect.set_defaults(handler=_cmd_connect)

    p_stream = sub.add_parser(
        "stream-test",
        help="Subscribe to closed 1d candles for the strategy portfolio (raw bar dump).",
    )
    _add_strategy_args(p_stream)
    p_stream.add_argument(
        "--max-candles",
        type=int,
        default=0,
        help="Stop after N candle events (0 = run until interrupted).",
    )
    p_stream.set_defaults(handler=_cmd_stream_test)

    args = parser.parse_args()
    try:
        args.handler(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
