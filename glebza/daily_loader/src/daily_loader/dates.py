"""Date windows for incremental daily ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class LoadWindows:
    """UTC half-open intervals [start, end) for each ingestion step."""

    as_of: datetime
    kline_start: datetime
    kline_end: datetime
    dividend_start: datetime
    dividend_end: datetime
    ruonia_start: datetime
    ruonia_end: datetime
    vol_start: datetime
    vol_end: datetime

    def to_dict(self) -> dict[str, str]:
        def fmt(value: datetime) -> str:
            return value.astimezone(timezone.utc).isoformat()

        return {
            "as_of": fmt(self.as_of),
            "kline_start": fmt(self.kline_start),
            "kline_end": fmt(self.kline_end),
            "dividend_start": fmt(self.dividend_start),
            "dividend_end": fmt(self.dividend_end),
            "ruonia_start": fmt(self.ruonia_start),
            "ruonia_end": fmt(self.ruonia_end),
            "vol_start": fmt(self.vol_start),
            "vol_end": fmt(self.vol_end),
        }


def _start_of_utc_day(value: datetime) -> datetime:
    utc = value.astimezone(timezone.utc)
    return datetime(utc.year, utc.month, utc.day, tzinfo=timezone.utc)


def _vol_calendar_days(lookback_period: int) -> int:
    """Calendar span wide enough to cover ``lookback_period`` daily trading bars."""
    return int(lookback_period * 365 / 252) + 14


def build_load_windows(
    *,
    as_of: datetime | None = None,
    kline_lookback_days: int = 1,
    dividend_lookback_days: int = 365,
    ruonia_lookback_days: int = 30,
    vol_lookback_period: int = 252,
) -> LoadWindows:
    """
    Build ingestion windows ending at the start of the UTC day after ``as_of``.

    Daily kline ingest uses a short lookback (default 1 day). Volatility reads a
    longer stored-history window from the DB so realized vol still uses 252 bars.
    """
    if kline_lookback_days <= 0:
        raise ValueError("kline_lookback_days must be positive")
    if dividend_lookback_days <= 0:
        raise ValueError("dividend_lookback_days must be positive")
    if ruonia_lookback_days <= 0:
        raise ValueError("ruonia_lookback_days must be positive")
    if vol_lookback_period <= 0:
        raise ValueError("vol_lookback_period must be positive")

    effective_as_of = as_of or datetime.now(timezone.utc)
    kline_end = _start_of_utc_day(effective_as_of)
    kline_start = kline_end - timedelta(days=kline_lookback_days)
    dividend_end = kline_end
    dividend_start = dividend_end - timedelta(days=dividend_lookback_days)
    ruonia_end = kline_end
    ruonia_start = ruonia_end - timedelta(days=ruonia_lookback_days)
    vol_end = kline_end
    vol_start = kline_end - timedelta(days=_vol_calendar_days(vol_lookback_period))

    return LoadWindows(
        as_of=effective_as_of,
        kline_start=kline_start,
        kline_end=kline_end,
        dividend_start=dividend_start,
        dividend_end=dividend_end,
        ruonia_start=ruonia_start,
        ruonia_end=ruonia_end,
        vol_start=vol_start,
        vol_end=vol_end,
    )


def build_period_windows(
    *,
    start_dt: datetime,
    end_dt: datetime,
    vol_lookback_period: int = 252,
) -> LoadWindows:
    """Build UTC windows [start, end) with the same bounds for klines, dividends, and RUONIA."""
    if end_dt <= start_dt:
        raise ValueError("end_dt must be after start_dt")
    if vol_lookback_period <= 0:
        raise ValueError("vol_lookback_period must be positive")

    start = start_dt.astimezone(timezone.utc)
    end = end_dt.astimezone(timezone.utc)
    vol_start = end - timedelta(days=_vol_calendar_days(vol_lookback_period))

    return LoadWindows(
        as_of=end,
        kline_start=start,
        kline_end=end,
        dividend_start=start,
        dividend_end=end,
        ruonia_start=start,
        ruonia_end=end,
        vol_start=vol_start,
        vol_end=end,
    )


def build_explicit_windows(
    *,
    kline_start: datetime,
    kline_end: datetime,
    dividend_lookback_days: int = 365,
    ruonia_lookback_days: int = 30,
) -> LoadWindows:
    """Build fixed UTC windows for one-off historical backfill."""
    if kline_end <= kline_start:
        raise ValueError("kline_end must be after kline_start")
    if dividend_lookback_days <= 0:
        raise ValueError("dividend_lookback_days must be positive")
    if ruonia_lookback_days <= 0:
        raise ValueError("ruonia_lookback_days must be positive")

    kline_start = kline_start.astimezone(timezone.utc)
    kline_end = kline_end.astimezone(timezone.utc)
    dividend_end = kline_end
    dividend_start = dividend_end - timedelta(days=dividend_lookback_days)
    ruonia_end = kline_end
    ruonia_start = ruonia_end - timedelta(days=ruonia_lookback_days)

    return LoadWindows(
        as_of=kline_end,
        kline_start=kline_start,
        kline_end=kline_end,
        dividend_start=dividend_start,
        dividend_end=dividend_end,
        ruonia_start=ruonia_start,
        ruonia_end=ruonia_end,
        vol_start=kline_start,
        vol_end=kline_end,
    )
