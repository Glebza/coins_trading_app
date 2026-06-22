"""Entry point: python -m transition_service <command>"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from repository.backtest_read_repository import BacktestReadRepository
from transition_service.promotion import PromotionService
from transition_service.settings import load_settings

logging.basicConfig(
    format="%(levelname)s: %(asctime)s %(message)s",
    level=logging.INFO,
)


def _format_dt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _format_pct(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, Decimal):
        value = float(value)
    return f"{float(value) * 100:.2f}%"


def _format_sharpe(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, Decimal):
        value = float(value)
    return f"{float(value):.2f}"


def _print_runs_table(runs: list[dict[str, Any]]) -> None:
    if not runs:
        print("no backtest runs found")
        return

    headers = ("id", "kline", "ann_return", "sharpe", "started_at", "status")
    rows = [
        (
            str(run["id"]),
            str(run["kline_interval"]),
            _format_pct(run.get("annualized_return")),
            _format_sharpe(run.get("sharpe")),
            _format_dt(run.get("started_at")),
            str(run["status"]),
        )
        for run in runs
    ]
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]

    def _line(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths))

    print(_line(headers))
    print(_line(tuple("-" * width for width in widths)))
    for row in rows:
        print(_line(row))


def _cmd_list_runs(args: argparse.Namespace) -> None:
    settings = load_settings()
    repo = BacktestReadRepository(settings)
    runs = repo.list_runs(status=args.status, limit=args.limit)
    _print_runs_table(runs)


def _cmd_promote(args: argparse.Namespace) -> None:
    settings = load_settings()
    service = PromotionService(settings)
    result = service.promote_run(args.run_id, dry_run=args.dry_run)

    if args.dry_run:
        logging.info(
            "dry-run promote run_id=%s would copy %s instruments (%s) and %s rules",
            result.backtest_run_id,
            result.instrument_count,
            ", ".join(result.instruments_copied) or "none new",
            result.rule_count,
        )
        return

    logging.info(
        "promoted backtest run_id=%s -> public strategy_id=%s portfolio_id=%s exchange_id=%s",
        result.backtest_run_id,
        result.live_strategy_id,
        result.live_portfolio_id,
        result.live_exchange_id,
    )
    if result.instruments_copied:
        logging.info("copied instruments to public: %s", ", ".join(result.instruments_copied))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote completed backtest runs from backtest DB to traderdb (public).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser(
        "list-runs",
        help="List backtest runs with kline period, annualised return, Sharpe, and launch date.",
    )
    list_parser.add_argument(
        "--status",
        default=None,
        help="Filter by run status (e.g. completed, failed, running).",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of rows to print.",
    )
    list_parser.set_defaults(handler=_cmd_list_runs)

    promote_parser = sub.add_parser(
        "promote",
        help="Copy strategy, portfolio, instruments, rules, and exchange from backtest DB to public.",
    )
    promote_parser.add_argument(
        "--run-id",
        type=int,
        required=True,
        help="backtests.backtest_runs.id to promote.",
    )
    promote_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report what would be copied without writing to public.",
    )
    promote_parser.set_defaults(handler=_cmd_promote)

    args = parser.parse_args()
    try:
        args.handler(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
