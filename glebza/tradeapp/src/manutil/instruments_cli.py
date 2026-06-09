"""CLI for T-Invest instrument metadata, klines, and volatility (Carver data prep)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_src = Path(__file__).resolve().parents[1]
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from exchanges.cbr_rates import CbrRatesService

logger = logging.getLogger(__name__)

_KLINE_INTERVALS = ("1m", "15m", "30m", "4h", "1d")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _add_kline_window_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--interval",
        required=True,
        choices=sorted(_KLINE_INTERVALS),
        help="Kline interval / table suffix (1m, 15m, 30m, 4h, 1d).",
    )
    parser.add_argument(
        "--start-dt",
        required=True,
        help="ISO datetime, e.g. 2025-01-01T00:00:00+00:00",
    )
    parser.add_argument(
        "--end-dt",
        required=True,
        help="ISO datetime, e.g. 2025-12-31T23:59:59+00:00",
    )


def _add_limit_shares_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--limit-shares",
        type=int,
        default=None,
        help="Optional max number of shares to process (debug).",
    )


def _add_date_window_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--start-dt",
        required=True,
        help="ISO datetime, e.g. 2025-01-01T00:00:00+00:00",
    )
    parser.add_argument(
        "--end-dt",
        required=True,
        help="ISO datetime, e.g. 2026-01-01T00:00:00+00:00",
    )


def _cmd_sync_shares(args: argparse.Namespace) -> dict:
    from exchanges.tinvest_broker import TBankInstrumentService
    from framework.instruments.instruments import InstrumentsService

    broker = TBankInstrumentService()
    persisted = broker.persist_tradeable_shares_to_db()
    svc = InstrumentsService()
    rows = svc.list_share_rows(limit=args.limit_shares)
    if args.json:
        print(json.dumps(rows, indent=2, default=str), flush=True)
    else:
        print(f"persisted_from_api={persisted} listed_in_db={len(rows)}", flush=True)
        for row in rows:
            print(
                f"{row['instruments_ticker']}\t"
                f"sector={row.get('sector')}\t"
                f"short={row.get('short_enabled_flag')}\t"
                f"class_code={row.get('class_code')}\t"
                f"lot={row.get('lot')}",
                flush=True,
            )
    return {"persisted_from_api": persisted, "listed_in_db": len(rows)}


def _cmd_load_klines_all(args: argparse.Namespace) -> dict:
    from framework.instruments.instruments import InstrumentsService

    svc = InstrumentsService()
    return svc.load_historical_klines(
        args.interval,
        start_dt=_parse_dt(args.start_dt),
        end_dt=_parse_dt(args.end_dt),
        limit=args.limit_shares,
    )


def _cmd_load_klines(args: argparse.Namespace) -> dict:
    from framework.instruments.instruments import InstrumentsService

    svc = InstrumentsService()
    return svc.load_klines_for_ticker(
        args.ticker.strip().upper(),
        args.interval,
        start_dt=_parse_dt(args.start_dt),
        end_dt=_parse_dt(args.end_dt),
    )


def _cmd_update_volatility(args: argparse.Namespace) -> dict:
    from framework.instruments.instruments import InstrumentsService

    svc = InstrumentsService()
    return svc.compute_and_store_volatility_all_shares(
        args.interval,
        start_dt=_parse_dt(args.start_dt),
        end_dt=_parse_dt(args.end_dt),
        lookback_period=args.lookback_period,
        limit=args.limit_shares,
    )


def _cmd_load_dividends_all(args: argparse.Namespace) -> dict:
    from framework.instruments.instruments import InstrumentsService

    svc = InstrumentsService()
    return svc.load_dividends_all_shares(
        start_dt=_parse_dt(args.start_dt),
        end_dt=_parse_dt(args.end_dt),
        limit=args.limit_shares,
        request_delay_seconds=args.request_delay_seconds,
        rate_limit_retries=args.rate_limit_retries,
        rate_limit_fallback_sleep_seconds=args.rate_limit_fallback_sleep_seconds,
    )


def _cmd_load_ruonia(args: argparse.Namespace) -> dict:
    from repository.funding_rate_repository import FundingRateRepository

    service = CbrRatesService()
    rows = service.fetch_ruonia(
        from_dt=_parse_dt(args.start_dt),
        to_dt=_parse_dt(args.end_dt),
    )
    stored = FundingRateRepository().upsert_funding_rates(rows)
    return {
        "fetched": len(rows),
        "stored": stored,
        "first_rate_date": rows[0]["rate_date"] if rows else None,
        "last_rate_date": rows[-1]["rate_date"] if rows else None,
    }


def main() -> None:
    logging.basicConfig(
        format="%(levelname)s: %(asctime)s %(message)s",
        level=logging.INFO,
    )

    parser = argparse.ArgumentParser(
        description="T-Invest instruments: metadata, klines, volatility.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser(
        "sync-shares",
        help="(1) Fetch tradable shares from T-Invest API and upsert metadata to PostgreSQL.",
    )
    p_sync.add_argument(
        "--json",
        action="store_true",
        help="Print full share rows as JSON after sync.",
    )
    _add_limit_shares_arg(p_sync)
    p_sync.set_defaults(handler=_cmd_sync_shares)

    p_all = sub.add_parser(
        "load-klines-all",
        help="(2) Upload klines for all shares for an interval and date range.",
    )
    _add_kline_window_args(p_all)
    _add_limit_shares_arg(p_all)
    p_all.set_defaults(handler=_cmd_load_klines_all)

    p_one = sub.add_parser(
        "load-klines",
        help="(3) Upload klines for one ticker, interval, and date range.",
    )
    p_one.add_argument("--ticker", required=True, help="instruments.ticker, e.g. SBER")
    _add_kline_window_args(p_one)
    p_one.set_defaults(handler=_cmd_load_klines)

    p_vol = sub.add_parser(
        "update-volatility",
        help="(4) Compute realized volatility from stored klines and save to DB.",
    )
    _add_kline_window_args(p_vol)
    p_vol.add_argument(
        "--lookback-period",
        type=int,
        default=252,
        help="Return observations for vol (e.g. 252 on daily bars).",
    )
    _add_limit_shares_arg(p_vol)
    p_vol.set_defaults(handler=_cmd_update_volatility)

    p_dividends = sub.add_parser(
        "load-dividends-all",
        help="Load dividend events for all shares from T-Invest into instrument_dividends.",
    )
    _add_date_window_args(p_dividends)
    _add_limit_shares_arg(p_dividends)
    p_dividends.add_argument(
        "--request-delay-seconds",
        type=float,
        default=0.5,
        help="Delay between T-Invest dividend requests to avoid rate limits. Default 0.5.",
    )
    p_dividends.add_argument(
        "--rate-limit-retries",
        type=int,
        default=3,
        help="Retry count for T-Invest RESOURCE_EXHAUSTED dividend requests. Default 3.",
    )
    p_dividends.add_argument(
        "--rate-limit-fallback-sleep-seconds",
        type=float,
        default=60.0,
        help="Fallback sleep if the rate-limit reset time is not present. Default 60.",
    )
    p_dividends.set_defaults(handler=_cmd_load_dividends_all)

    p_ruonia = sub.add_parser(
        "load-ruonia",
        help="Load RUONIA funding rates from Bank of Russia into funding_rates.",
    )
    _add_date_window_args(p_ruonia)
    p_ruonia.set_defaults(handler=_cmd_load_ruonia)

    args = parser.parse_args()
    result = args.handler(args)
    if args.command != "sync-shares" or not args.json:
        print(result, flush=True)


if __name__ == "__main__":
    main()
