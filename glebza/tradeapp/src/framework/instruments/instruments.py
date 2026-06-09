"""Batch helpers for T-Invest share instruments."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from math import sqrt
from typing import Optional

import pandas as pd

from framework.instruments.instrument import TInvestInstrumentApiService
from repository.history_repository import HistoryRepository
from repository.instrument_dividend_repository import InstrumentDividendRepository
from repository.tinvest_repository import TinvestRepository

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_RATE_LIMIT_RESET_RE = re.compile(r"ratelimit_reset=['\"]?(\d+(?:\.\d+)?)")

_ANNUALIZATION_FACTORS: dict[str, int] = {
    "1m": 252 * 390,
    "15m": 252 * 26,
    "30m": 252 * 13,
    "4h": 252 * 2,
    "1d": 252,
}


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _min_klines_for_period(
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    *,
    min_coverage: float,
) -> int:
    if not 0 < min_coverage <= 1:
        raise ValueError("min_kline_coverage must be in (0, 1]")
    calendar_days = (end_dt - start_dt).days
    if calendar_days <= 0:
        raise ValueError("kline_end_dt must be after kline_start_dt")

    periods_per_year = _ANNUALIZATION_FACTORS.get(interval)
    if periods_per_year is None:
        raise ValueError(f"unsupported kline interval '{interval}'")

    expected_bars = max(1, int(calendar_days * periods_per_year / 365))
    return max(1, int(expected_bars * min_coverage))


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or "resource exhausted" in text.lower() or "ratelimit_reset" in text


def _is_dividend_not_found_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code is None:
        return False
    return getattr(code, "name", None) == "NOT_FOUND"


def _rate_limit_sleep_seconds(exc: Exception, *, fallback: float) -> float:
    match = _RATE_LIMIT_RESET_RE.search(str(exc))
    if not match:
        return fallback
    return max(0.0, float(match.group(1)) + 1.0)


class InstrumentsService:
    def __init__(self, token: Optional[str] = None, *, target: Optional[str] = None) -> None:
        self._instrument_repo = TinvestRepository()
        self._history_repo = HistoryRepository()
        self._dividend_repo = InstrumentDividendRepository()
        self._token = token
        self._target = target
        self._api_service: Optional[TInvestInstrumentApiService] = None

    def _get_api_service(self) -> TInvestInstrumentApiService:
        if self._api_service is None:
            self._api_service = TInvestInstrumentApiService(token=self._token, target=self._target)
        return self._api_service

    def filter_shares(
        self,
        *,
        kline_interval: str = "1d",
        volatility_interval: str = "1d",
        volume_percentile: float = 0.60,
        volatility_percentile: float = 0.60,
        kline_start_dt: Optional[datetime] = None,
        kline_end_dt: Optional[datetime] = None,
        min_klines: Optional[int] = None,
        min_kline_coverage: float = 0.80,
        exclude_for_qual_investor: bool = True,
    ) -> list[dict]:
        """
        Universe filter: median kline volume and latest stored vol above cross-sectional thresholds.

        Requires populated ``kline_{interval}`` and ``instrument_volatility`` in the DB
        (see ``manutil`` load-klines / update-volatility). Uses ``DATABASE_URL`` and
        ``DATABASE_DEFAULT_SCHEMA`` (e.g. ``public`` or ``backtests``).
        """
        shares = self._instrument_repo.list_shares_filtered_by_liquidity_and_volatility(
            kline_interval=kline_interval,
            volatility_interval=volatility_interval,
            volume_percentile=volume_percentile,
            volatility_percentile=volatility_percentile,
            kline_start_dt=_normalize_dt(kline_start_dt),
            exclude_for_qual_investor=exclude_for_qual_investor,
        )
        if kline_end_dt is None:
            return shares

        start_dt = _normalize_dt(kline_start_dt)
        end_dt = _normalize_dt(kline_end_dt)
        if start_dt is None:
            raise ValueError("kline_start_dt is required when kline_end_dt is set")

        required = min_klines or _min_klines_for_period(
            kline_interval, start_dt, end_dt, min_coverage=min_kline_coverage
        )
        instrument_ids = self._instrument_repo.instrument_ids_with_min_kline_count(
            [int(share["instrument_id"]) for share in shares],
            kline_interval,
            start_dt=start_dt,
            end_dt=end_dt,
            min_count=required,
        )
        kept = [share for share in shares if int(share["instrument_id"]) in instrument_ids]
        dropped = len(shares) - len(kept)
        if dropped:
            logger.info(
                "dropped %s shares with fewer than %s klines in [%s, %s] interval=%s",
                dropped,
                required,
                start_dt,
                end_dt,
                kline_interval,
            )
        return kept

    def list_share_rows(self, limit: Optional[int] = None) -> list[dict]:
        shares = self._instrument_repo.list_shares(limit=limit)
        result: list[dict] = []
        seen: set[str] = set()
        for share in shares:
            ticker = share["instruments_ticker"]
            class_code = share["class_code"]
            if ticker and class_code and ticker not in seen:
                result.append(share)
                seen.add(ticker)
        return result

    def _resolve_share(self, ticker: str) -> dict:
        share = self._instrument_repo.get_by_ticker(ticker)
        if not share:
            raise ValueError(f"Ticker '{ticker}' is not present in instruments/instrument_share")
        return share

    def persist_share(
        self,
        share: dict,
        interval: str,
        *,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> dict:
        """Fetch share metadata + klines from T-Invest and persist both."""
        ticker = share["instruments_ticker"]
        figi = share.get("figi")
        if not figi:
            raise ValueError(f"share row missing figi for ticker={ticker}")
        return self._get_api_service().sync_share_from_api(
            figi,
            ticker,
            interval,
            self._instrument_repo,
            from_dt=from_dt,
            to_dt=to_dt,
        )

    def persist_candles(
        self,
        share: dict,
        interval: str,
        *,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> int:
        """Persist klines and refresh share metadata from T-Invest."""
        return self.persist_share(
            share,
            interval,
            from_dt=from_dt,
            to_dt=to_dt,
        )["inserted_klines"]

    def persist_all_share_candles(
        self,
        interval: str,
        *,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> dict[str, int]:
        result: dict[str, int] = {}
        for share in self.list_share_rows(limit=limit):
            ticker = share["instruments_ticker"]
            result[ticker] = self.persist_share(
                share,
                interval,
                from_dt=from_dt,
                to_dt=to_dt,
            )["inserted_klines"]
        return result

    def get_candles_dataframe(
        self,
        ticker: str,
        interval: str,
        *,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        share = self._resolve_share(ticker)
        return self._get_candles_dataframe_for_share(
            share,
            interval,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
        )

    def _get_candles_dataframe_for_share(
        self,
        share: dict,
        interval: str,
        *,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        rows = self._history_repo.get_klines_by_instrument(
            share["instrument_id"],
            interval,
            start_dt=_normalize_dt(start_dt),
            end_dt=_normalize_dt(end_dt),
            limit=limit,
        )
        df = pd.DataFrame(rows)
        if df.empty:
            return df

        df = df.sort_values("k_interval").reset_index(drop=True)
        df["k_interval"] = pd.to_datetime(df["k_interval"], utc=True)
        for column in ["open_price", "high_price", "low_price", "close_price", "volume"]:
            df[column] = pd.to_numeric(df[column])
        return df

    def calculate_volatility(
        self,
        ticker: str,
        interval: str,
        *,
        lookback_period: int = 20,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> tuple[pd.DataFrame, Decimal]:
        share = self._resolve_share(ticker)
        return self._calculate_volatility_for_share(
            share,
            interval,
            lookback_period=lookback_period,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
        )

    def _calculate_volatility_for_share(
        self,
        share: dict,
        interval: str,
        *,
        lookback_period: int = 252,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> tuple[pd.DataFrame, Decimal]:
        ticker = share["instruments_ticker"]
        df = self._get_candles_dataframe_for_share(
            share,
            interval,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
        )
        if df.empty or len(df.index) < 2:
            raise ValueError(f"Not enough candles in PostgreSQL for ticker='{ticker}' interval='{interval}'")

        if len(df.index) > lookback_period + 1:
            df = df.tail(lookback_period + 1).reset_index(drop=True)

        df["return"] = df["close_price"].pct_change()
        returns = df["return"].dropna()
        if returns.empty:
            raise ValueError(f"Not enough completed returns to calculate volatility for '{ticker}'")

        annualization_factor = _ANNUALIZATION_FACTORS[interval]
        realized_vol = returns.std(ddof=1) * sqrt(annualization_factor)
        if pd.isna(realized_vol):
            raise ValueError(f"Failed to calculate volatility for '{ticker}'")
        return df, Decimal(str(realized_vol))

    def calculate_and_store_volatility(
        self,
        ticker: str,
        interval: str,
        *,
        lookback_period: int = 252,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> dict:
        share = self._resolve_share(ticker)
        return self._calculate_and_store_volatility_for_share(
            share,
            interval,
            lookback_period=lookback_period,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
        )

    def _calculate_and_store_volatility_for_share(
        self,
        share: dict,
        interval: str,
        *,
        lookback_period: int = 20,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> dict:
        ticker = share["instruments_ticker"]
        df, volatility = self._calculate_volatility_for_share(
            share,
            interval,
            lookback_period=lookback_period,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
        )
        as_of = df.iloc[-1]["k_interval"].to_pydatetime()
        observations = len(df["return"].dropna())
        self._history_repo.save_instrument_volatility(
            share["instrument_id"],
            interval,
            as_of,
            lookback_period,
            volatility,
            observations,
        )
        logger.info(
            "saved_volatility ticker=%s interval=%s as_of=%s value=%s",
            ticker,
            interval,
            as_of,
            volatility,
        )
        return {
            "ticker": ticker,
            "interval": interval,
            "as_of": as_of,
            "volatility": volatility,
            "observations": observations,
        }

    def load_klines_for_ticker(
        self,
        ticker: str,
        interval: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict:
        """Fetch metadata + candles from T-Invest for one ticker and persist."""
        share = self._resolve_share(ticker)
        return self.persist_share(
            share,
            interval,
            from_dt=start_dt,
            to_dt=end_dt,
        )

    def load_historical_klines(
        self,
        interval: str,
        start_dt: datetime,
        end_dt: datetime,
        *,
        limit: Optional[int] = None,
    ) -> dict[str, dict]:
        """Fetch share metadata and candles from T-Invest for all listed shares (no volatility)."""
        result: dict[str, dict] = {}
        for share in self.list_share_rows(limit=limit):
            ticker = share["instruments_ticker"]
            try:
                synced = self.persist_share(
                    share,
                    interval,
                    from_dt=start_dt,
                    to_dt=end_dt,
                )
                result[ticker] = {
                    "inserted_klines": synced["inserted_klines"],
                    "sector": synced["sector"],
                    "short_enabled_flag": synced["short_enabled_flag"],
                }
            except Exception as exc:
                logger.exception("failed to load klines ticker=%s interval=%s", ticker, interval)
                result[ticker] = {"error": str(exc)}
        return result

    def load_dividends_for_ticker(
        self,
        ticker: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict:
        """Fetch dividend events from T-Invest for one ticker and persist them."""
        share = self._resolve_share(ticker)
        return self._load_dividends_for_share(share, start_dt, end_dt)

    def load_dividends_all_shares(
        self,
        start_dt: datetime,
        end_dt: datetime,
        *,
        limit: Optional[int] = None,
        request_delay_seconds: float = 0.5,
        rate_limit_retries: int = 3,
        rate_limit_fallback_sleep_seconds: float = 60.0,
    ) -> dict[str, dict]:
        """Fetch and persist dividend events for all listed shares."""
        if request_delay_seconds < 0:
            raise ValueError("request_delay_seconds must be non-negative")
        if rate_limit_retries < 0:
            raise ValueError("rate_limit_retries must be non-negative")
        if rate_limit_fallback_sleep_seconds < 0:
            raise ValueError("rate_limit_fallback_sleep_seconds must be non-negative")

        result: dict[str, dict] = {}
        shares = self.list_share_rows(limit=limit)
        for index, share in enumerate(shares):
            ticker = share["instruments_ticker"]
            try:
                result[ticker] = self._load_dividends_for_share_with_retries(
                    share,
                    start_dt,
                    end_dt,
                    rate_limit_retries=rate_limit_retries,
                    rate_limit_fallback_sleep_seconds=rate_limit_fallback_sleep_seconds,
                )
            except Exception as exc:
                logger.exception("failed dividends ticker=%s", ticker)
                result[ticker] = {"error": str(exc)}
            if request_delay_seconds and index < len(shares) - 1:
                time.sleep(request_delay_seconds)
        return result

    def _load_dividends_for_share_with_retries(
        self,
        share: dict,
        start_dt: datetime,
        end_dt: datetime,
        *,
        rate_limit_retries: int,
        rate_limit_fallback_sleep_seconds: float,
    ) -> dict:
        ticker = share["instruments_ticker"]
        for attempt in range(rate_limit_retries + 1):
            try:
                return self._load_dividends_for_share(share, start_dt, end_dt)
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt >= rate_limit_retries:
                    raise
                sleep_seconds = _rate_limit_sleep_seconds(exc, fallback=rate_limit_fallback_sleep_seconds)
                logger.warning(
                    "rate limited while loading dividends ticker=%s attempt=%s/%s sleep_seconds=%.1f",
                    ticker,
                    attempt + 1,
                    rate_limit_retries,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

        raise RuntimeError(f"failed to load dividends for ticker={ticker}")

    def _load_dividends_for_share(
        self,
        share: dict,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict:
        ticker = share["instruments_ticker"]
        try:
            dividends = self._get_api_service().fetch_dividends_by_share(
                share,
                start_dt,
                end_dt,
            )
        except Exception as exc:
            if _is_dividend_not_found_error(exc):
                logger.warning(
                    "skipping dividends ticker=%s: instrument not found in T-Invest",
                    ticker,
                )
                return {
                    "ticker": ticker,
                    "skipped": True,
                    "skip_reason": "not_found",
                    "fetched_dividends": 0,
                    "stored_dividends": 0,
                }
            raise
        stored = self._dividend_repo.upsert_dividends(
            int(share["instrument_id"]),
            dividends,
        )
        logger.info(
            "saved_dividends ticker=%s fetched=%s stored=%s",
            ticker,
            len(dividends),
            stored,
        )
        return {
            "ticker": ticker,
            "fetched_dividends": len(dividends),
            "stored_dividends": stored,
        }

    def compute_and_store_volatility_all_shares(
        self,
        interval: str,
        start_dt: datetime,
        end_dt: datetime,
        *,
        lookback_period: int = 252,
        limit: Optional[int] = None,
    ) -> dict[str, dict]:
        """Read klines from PostgreSQL and write realized volatility for all shares (no API fetch)."""
        result: dict[str, dict] = {}
        for share in self.list_share_rows(limit=limit):
            ticker = share["instruments_ticker"]
            try:
                vol_row = self._calculate_and_store_volatility_for_share(
                    share,
                    interval,
                    lookback_period=lookback_period,
                    start_dt=start_dt,
                    end_dt=end_dt,
                )
                result[ticker] = {
                    "volatility": str(vol_row["volatility"]),
                    "as_of": vol_row["as_of"],
                    "observations": vol_row["observations"],
                }
            except Exception as exc:
                logger.exception("failed volatility ticker=%s interval=%s", ticker, interval)
                result[ticker] = {"error": str(exc)}
        return result