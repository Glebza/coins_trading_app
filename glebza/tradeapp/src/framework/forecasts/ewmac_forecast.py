"""Carver-style EWMAC forecast.

EWMAC is the difference between a fast and slow exponentially weighted moving
average, divided by recent price-change volatility, multiplied by a forecast
scalar, and capped to the Carver forecast range.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FORECAST_FLOOR = -20.0
FORECAST_CAP = 20.0
FORECAST_STEP = 5.0

EWMAC_FORECAST_SCALARS: dict[tuple[int, int], float] = {
    (2, 8): 10.6,
    (4, 16): 7.5,
    (8, 32): 5.3,
    (16, 64): 3.75,
    (32, 128): 2.65,
    (64, 256): 1.87,
}


@dataclass(frozen=True)
class EWMACConfig:
    """Parameters for one EWMAC rule variation."""

    fast_span: int = 16
    slow_span: int = 64
    volatility_span: int = 35
    forecast_scalar: float | None = None
    forecast_floor: float = FORECAST_FLOOR
    forecast_cap: float = FORECAST_CAP
    forecast_step: float = FORECAST_STEP

    def __post_init__(self) -> None:
        if self.fast_span <= 0:
            raise ValueError("fast_span must be positive")
        if self.slow_span <= self.fast_span:
            raise ValueError("slow_span must be greater than fast_span")
        if self.volatility_span <= 1:
            raise ValueError("volatility_span must be greater than 1")
        if self.forecast_step <= 0:
            raise ValueError("forecast_step must be positive")

    @property
    def scalar(self) -> float:
        if self.forecast_scalar is not None:
            return self.forecast_scalar
        return EWMAC_FORECAST_SCALARS[(self.fast_span, self.slow_span)]


def price_volatility_series(close_prices: pd.Series, *, span: int = 35) -> pd.Series:
    """Recent standard deviation of daily price changes in price points."""
    closes = pd.to_numeric(close_prices).astype("float64")
    min_periods = max(2, min(span // 2, 10))
    return closes.diff().ewm(span=span, min_periods=min_periods, adjust=False).std()


def ewmac_raw_forecast_series(klines: pd.DataFrame, config: EWMACConfig = EWMACConfig()) -> pd.Series:
    """Raw EWMAC crossover: fast EWMA minus slow EWMA."""

    closes = pd.to_numeric(klines["close_price"]).astype("float64")
    fast_ewma = closes.ewm(span=config.fast_span, min_periods=config.fast_span, adjust=False).mean()
    slow_ewma = closes.ewm(span=config.slow_span, min_periods=config.slow_span, adjust=False).mean()
    return fast_ewma - slow_ewma


def ewmac_volatility_adjusted_series(
    klines: pd.DataFrame,
    config: EWMACConfig = EWMACConfig(),
) -> pd.Series:
    """Raw EWMAC divided by recent price volatility."""
    raw = ewmac_raw_forecast_series(klines, config)
    price_volatility = price_volatility_series(klines["close_price"], span=config.volatility_span)
    adjusted = raw / price_volatility.replace(0.0, np.nan)
    return adjusted.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def cap_forecast(
    forecast: float | pd.Series,
    *,
    floor: float = FORECAST_FLOOR,
    cap: float = FORECAST_CAP,
) -> float | pd.Series:
    """Clip a forecast to Carver's allowed forecast range."""
    if isinstance(forecast, pd.Series):
        return forecast.clip(lower=floor, upper=cap)

    return max(floor, min(cap, float(forecast)))


def bucket_forecast(
    forecast: float | pd.Series,
    *,
    floor: float = FORECAST_FLOOR,
    cap: float = FORECAST_CAP,
    step: float = FORECAST_STEP,
) -> float | pd.Series:
    """Optional human-readable forecast buckets: -20, -15, ..., +20."""
    capped = cap_forecast(forecast, floor=floor, cap=cap)
    if isinstance(capped, pd.Series):
        return (capped / step).round() * step
    return round(capped / step) * step


def ewmac_forecast_series(klines: pd.DataFrame, config: EWMACConfig = EWMACConfig()) -> pd.Series:
    """Capped EWMAC forecast for backtests."""
    forecast = ewmac_volatility_adjusted_series(klines, config) * config.scalar
    return cap_forecast(
        forecast,
        floor=config.forecast_floor,
        cap=config.forecast_cap,
    )


def ewmac_forecast_last(klines: pd.DataFrame, config: EWMACConfig = EWMACConfig()) -> float:
    """Latest capped EWMAC forecast for real-time trading."""
    return float(ewmac_forecast_series(klines, config).iloc[-1])
