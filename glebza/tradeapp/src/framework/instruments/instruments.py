"""Batch helpers for T-Invest share instruments."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from decimal import Decimal
from math import sqrt
from typing import Optional

import pandas as pd

from framework.instruments.instrument import TInvestKlineService, _INTERVALS, _parse_dt
from repository.history_repository import HistoryRepository
from repository.tinvest_repository import TinvestRepository

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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


class TInvestInstrumentsService:
    def __init__(self, token: Optional[str] = None, *, target: Optional[str] = None) -> None:
        self._instrument_repo = TinvestRepository()
        self._history_repo = HistoryRepository()
        self._kline_service = TInvestKlineService(token=token, target=target)

    def list_share_tickers(self, limit: Optional[int] = None) -> list[str]:
        return [share["instruments_ticker"] for share in self.list_share_rows(limit=limit) if share["instruments_ticker"]]

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

    def persist_candles(
        self,
        share: dict,
        interval: str,
        *,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> int:
        return self._kline_service.persist_candles(
            share["instrument_id"],
            share["instruments_ticker"],
            share["class_code"],
            interval,
            from_dt=from_dt,
            to_dt=to_dt,
        )

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
            result[ticker] = self.persist_candles(
                share,
                interval,
                from_dt=from_dt,
                to_dt=to_dt,
            )
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
        lookback_period: int = 20,
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
        lookback_period: int = 20,
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

    def load_candles_and_store_volatility(
        self,
        interval: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for share in self.list_share_rows():
            ticker = share["instruments_ticker"]
            try:
                inserted = self.persist_candles(
                    share,
                    interval,
                    from_dt=start_dt,
                    to_dt=end_dt,
                )
                #volatility = self._calculate_and_store_volatility_for_share(
                #    share,
                #    interval,
                #    start_dt=start_dt,
                #    end_dt=end_dt,
                #)
                result[ticker] = {
                    "inserted_klines": inserted,
                    #"volatility": volatility["volatility"],
                    #"as_of": volatility["as_of"],
                    #"observations": volatility["observations"],
                }
            except Exception as exc:
                logger.exception("failed to process ticker=%s interval=%s", ticker, interval)
                result[ticker] = {"error": str(exc)}
        return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load T-Invest share candles for all tickers and store realized volatility"
    )
    parser.add_argument("--interval", required=True, choices=sorted(_INTERVALS))
    parser.add_argument("--start-dt", required=True, help="ISO datetime, e.g. 2024-01-01T00:00:00+00:00")
    parser.add_argument("--end-dt", required=True, help="ISO datetime, e.g. 2024-02-01T00:00:00+00:00")
    args = parser.parse_args()
    svc = TInvestInstrumentsService()

    result = svc.load_candles_and_store_volatility(
        args.interval,
        start_dt=_parse_dt(args.start_dt),
        end_dt=_parse_dt(args.end_dt),
    )
    print(result, flush=True)


if __name__ == "__main__":
    main()