"""Entry point: python -m daily_loader <command>"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from daily_loader.dates import build_load_windows, build_period_windows
from daily_loader.pipeline import run_backfill, run_pipeline
from daily_loader.settings import load_settings
from daily_loader.steps import (
    check_tinvest_api,
    load_dividends_all,
    load_klines_all,
    load_ruonia,
    sync_shares,
)

logging.basicConfig(
    format="%(levelname)s: %(asctime)s %(message)s",
    level=logging.INFO,
)

_KLINE_INTERVALS = ("1m", "15m", "30m", "4h", "1d")


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _add_period_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--start-dt",
        required=True,
        help="ISO datetime, e.g. 2020-01-01T00:00:00+00:00",
    )
    parser.add_argument(
        "--end-dt",
        required=True,
        help="ISO datetime, e.g. 2026-06-01T00:00:00+00:00",
    )


def _report(step: str, payload: dict) -> None:
    logging.info("done %s %s", step, payload)
    if int(payload.get("errors", 0)) > 0:
        raise SystemExit(1)


def _finish_pipeline(result) -> None:
    for name, payload in result.steps.items():
        logging.info("done %s %s", name, payload)
    total_errors = sum(int(step.get("errors", 0)) for step in result.steps.values())
    if total_errors:
        raise SystemExit(1)


def _period_windows(args: argparse.Namespace):
    settings = load_settings()
    return build_period_windows(
        start_dt=_parse_dt(args.start_dt),
        end_dt=_parse_dt(args.end_dt),
        vol_lookback_period=settings.vol_lookback_period,
    ), settings


def _cmd_check_tinvest(_args: argparse.Namespace) -> None:
    payload = check_tinvest_api()
    logging.info("done check-tinvest %s", payload)


def _cmd_sync_shares(_args: argparse.Namespace) -> None:
    _report("sync-shares", sync_shares())


def _cmd_load_klines(args: argparse.Namespace) -> None:
    windows, settings = _period_windows(args)
    interval = args.interval or settings.kline_interval
    _report(
        "load-klines",
        load_klines_all(windows, interval=interval, settings=settings),
    )


def _cmd_load_dividends(args: argparse.Namespace) -> None:
    windows, settings = _period_windows(args)
    _report("load-dividends", load_dividends_all(windows, settings=settings))


def _cmd_load_ruonia(args: argparse.Namespace) -> None:
    windows, _settings = _period_windows(args)
    _report("load-ruonia", load_ruonia(windows))


def _cmd_run(_args: argparse.Namespace) -> None:
    _finish_pipeline(run_pipeline())


def _cmd_backfill(args: argparse.Namespace) -> None:
    settings = load_settings()
    windows = build_period_windows(
        start_dt=_parse_dt(args.start_dt),
        end_dt=_parse_dt(args.end_dt),
        vol_lookback_period=settings.vol_lookback_period,
    )
    _finish_pipeline(run_backfill(windows, settings=settings))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="T-Invest daily data loader: granular CLI for initial setup, run for daily cron.",
    )
    sub = parser.add_subparsers(dest="command")

    check_parser = sub.add_parser(
        "check-tinvest",
        help="Verify T-Invest gRPC connectivity and INVEST_TOKEN (no DB writes).",
    )
    check_parser.set_defaults(handler=_cmd_check_tinvest)

    sync_parser = sub.add_parser(
        "sync-shares",
        help="Fetch tradeable share metadata from T-Invest and upsert into the DB.",
    )
    sync_parser.set_defaults(handler=_cmd_sync_shares)

    klines_parser = sub.add_parser(
        "load-klines",
        help="Load klines for all shares in the DB over --start-dt .. --end-dt.",
    )
    _add_period_args(klines_parser)
    klines_parser.add_argument(
        "--interval",
        choices=_KLINE_INTERVALS,
        default=None,
        help="Kline interval (default: DAILY_LOADER_KLINE_INTERVAL or 1d).",
    )
    klines_parser.set_defaults(handler=_cmd_load_klines)

    dividends_parser = sub.add_parser(
        "load-dividends",
        help="Load dividend events for all shares in the DB over --start-dt .. --end-dt.",
    )
    _add_period_args(dividends_parser)
    dividends_parser.set_defaults(handler=_cmd_load_dividends)

    ruonia_parser = sub.add_parser(
        "load-ruonia",
        help="Load RUONIA funding rates from CBR over --start-dt .. --end-dt.",
    )
    _add_period_args(ruonia_parser)
    ruonia_parser.set_defaults(handler=_cmd_load_ruonia)

    run_parser = sub.add_parser(
        "run",
        help="Daily cron: sync-shares + 1-day klines/dividends/RUONIA + volatility.",
    )
    run_parser.set_defaults(handler=_cmd_run)
    parser.set_defaults(handler=_cmd_run)

    backfill_parser = sub.add_parser(
        "backfill",
        help="Run all ingestion steps (including volatility) for an explicit date range.",
    )
    _add_period_args(backfill_parser)
    backfill_parser.set_defaults(handler=_cmd_backfill)

    args = parser.parse_args()
    try:
        args.handler(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
