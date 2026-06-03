"""Carver-style equity carry forecast."""

from __future__ import annotations

from datetime import timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from glebza.tradeapp.src.framework.forecasts.ewmac_forecast import FORECAST_CAP, FORECAST_FLOOR, cap_forecast

CARRY_FORECAST_SCALAR = 30.0


def calculate_equity_carry_raw(
    dividend_yield: float | pd.Series,
    funding_rate: float | pd.Series,
    annualized_volatility: float | pd.Series,
) -> float | pd.Series:
    """Volatility-standardised equity carry: (dividend yield - funding rate) / vol."""
    raw = (dividend_yield - funding_rate) / annualized_volatility
    if isinstance(raw, pd.Series):
        return raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return float(raw)


def calculate_equity_carry_forecast(
    dividend_yield: float | pd.Series,
    funding_rate: float | pd.Series,
    annualized_volatility: float | pd.Series,
    *,
    scalar: float = CARRY_FORECAST_SCALAR,
    floor: float = FORECAST_FLOOR,
    cap: float = FORECAST_CAP,
) -> float | pd.Series:
    """Scaled and capped equity carry forecast."""
    raw = calculate_equity_carry_raw(dividend_yield, funding_rate, annualized_volatility)
    return cap_forecast(raw * scalar, floor=floor, cap=cap)


def calculate_annual_dividend_yield_series(
    klines: pd.DataFrame,
    dividends: Iterable[dict],
    *,
    lookback_days: int = 365,
) -> pd.Series:
    """Trailing known dividend yield for each kline date.

    Dividend events are included only when they were known by the forecast date
    using ``api_created_at`` first and ``declared_date`` as fallback.
    """
    rows = klines.copy()
    rows["k_interval"] = pd.to_datetime(rows["k_interval"], utc=True)
    rows["close_price"] = pd.to_numeric(rows["close_price"]).astype("float64")

    dividend_rows = pd.DataFrame(list(dividends))
    if dividend_rows.empty:
        return pd.Series(0.0, index=rows.index)

    dividend_rows["record_date"] = pd.to_datetime(dividend_rows["record_date"], utc=True)
    dividend_rows["dividend_net"] = pd.to_numeric(dividend_rows["dividend_net"]).astype("float64")
    dividend_rows["known_at"] = calculate_known_at_series(dividend_rows)

    values: list[float] = []
    for _, row in rows.iterrows():
        as_of = row["k_interval"]
        window_start = as_of - timedelta(days=lookback_days)
        known_dividends = dividend_rows[
            (dividend_rows["record_date"] > window_start)
            & (dividend_rows["record_date"] <= as_of)
            & (dividend_rows["known_at"] <= as_of)
        ]
        close_price = float(row["close_price"])
        values.append(float(known_dividends["dividend_net"].sum()) / close_price)
    return pd.Series(values, index=rows.index)


def calculate_funding_rate_series(klines: pd.DataFrame, funding_rates: Iterable[dict]) -> pd.Series:
    """Latest-known annual funding rate for each kline date."""
    rows = klines.copy()
    rows["k_interval"] = pd.to_datetime(rows["k_interval"], utc=True)

    rate_rows = pd.DataFrame(list(funding_rates))
    if rate_rows.empty:
        return pd.Series(0.0, index=rows.index)

    rate_rows["rate_date"] = pd.to_datetime(rate_rows["rate_date"], utc=True)
    rate_rows["annual_rate"] = pd.to_numeric(rate_rows["annual_rate"]).astype("float64")
    if "published_at" in rate_rows:
        rate_rows["known_at"] = pd.to_datetime(rate_rows["published_at"], utc=True)
    else:
        rate_rows["known_at"] = rate_rows["rate_date"] + pd.Timedelta(days=1)
    rate_rows["known_at"] = rate_rows["known_at"].fillna(rate_rows["rate_date"] + pd.Timedelta(days=1))

    values: list[float] = []
    for _, row in rows.iterrows():
        known_rates = rate_rows[rate_rows["known_at"] <= row["k_interval"]]
        if known_rates.empty:
            values.append(0.0)
        else:
            values.append(float(known_rates.sort_values("rate_date").iloc[-1]["annual_rate"]))
    return pd.Series(values, index=rows.index)


def add_carry_forecast_columns(
    klines: pd.DataFrame,
    dividends: Iterable[dict],
    funding_rates: Iterable[dict],
    annualized_volatility: float | pd.Series,
    *,
    lookback_days: int = 365,
    scalar: float = CARRY_FORECAST_SCALAR,
) -> pd.DataFrame:
    """Add dividend yield, funding rate, and carry forecast columns."""
    rows = klines.copy()
    dividend_yield = calculate_annual_dividend_yield_series(rows, dividends, lookback_days=lookback_days)
    funding = calculate_funding_rate_series(rows, funding_rates)
    rows["dividend_yield"] = dividend_yield
    rows["funding_rate"] = funding
    rows["forecast_carry"] = calculate_equity_carry_forecast(
        dividend_yield,
        funding,
        annualized_volatility,
        scalar=scalar,
    )
    return rows


def calculate_known_at_series(dividend_rows: pd.DataFrame) -> pd.Series:
    known_at = pd.Series(pd.NaT, index=dividend_rows.index, dtype="datetime64[ns, UTC]")
    if "declared_date" in dividend_rows:
        known_at = pd.to_datetime(dividend_rows["declared_date"], utc=True)
    if "api_created_at" in dividend_rows:
        api_created_at = pd.to_datetime(dividend_rows["api_created_at"], utc=True)
        known_at = api_created_at.fillna(known_at)
    elif "created_at" in dividend_rows:
        api_created_at = pd.to_datetime(dividend_rows["created_at"], utc=True)
        known_at = api_created_at.fillna(known_at)
    return known_at
