"""Forecast diversification multiplier (FDM) helpers."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Mapping

import numpy as np
import pandas as pd


DEFAULT_FDM_FLOOR = 1.0
DEFAULT_FDM_CAP = 2.5


@dataclass(frozen=True)
class ForecastDiversificationDiagnostics:
    """Diagnostics used to scale a weighted forecast combination."""

    multiplier: float
    correlation: pd.DataFrame
    average_correlation: float


def calculate_forecast_correlation(
    forecasts: Mapping[str, pd.Series],
    *,
    min_periods: int = 20,
) -> pd.DataFrame:
    """Estimate the correlation matrix between forecast variation series."""
    if not forecasts:
        raise ValueError("forecasts must not be empty")

    frame = pd.DataFrame(
        {name: pd.to_numeric(series, errors="coerce").astype("float64") for name, series in forecasts.items()}
    ).replace([np.inf, -np.inf], np.nan)
    names = list(forecasts.keys())
    if len(names) == 1:
        return pd.DataFrame([[1.0]], index=names, columns=names)

    correlation = frame.corr(min_periods=min_periods).reindex(index=names, columns=names)
    correlation = correlation.fillna(1.0).clip(lower=-1.0, upper=1.0)
    for name in names:
        correlation.loc[name, name] = 1.0
    return correlation


def calculate_average_correlation(correlation: pd.DataFrame) -> float:
    """Average off-diagonal correlation; 1.0 for a single forecast."""
    if len(correlation.index) <= 1:
        return 1.0

    mask = ~np.eye(len(correlation.index), dtype=bool)
    values = correlation.to_numpy(dtype="float64")[mask]
    if len(values) == 0:
        return 1.0
    return float(np.nanmean(values))


def calculate_forecast_diversification_multiplier(
    correlation: pd.DataFrame,
    weights: Mapping[str, float],
    *,
    floor: float = DEFAULT_FDM_FLOOR,
    cap: float = DEFAULT_FDM_CAP,
) -> float:
    """Calculate FDM from forecast weights and their correlation matrix."""
    if floor <= 0:
        raise ValueError("floor must be positive")
    if cap < floor:
        raise ValueError("cap must be greater than or equal to floor")

    names = [name for name in weights if name in correlation.index]
    if not names:
        return floor

    weight_values = np.array([float(weights[name]) for name in names], dtype="float64")
    weight_sum = float(np.abs(weight_values).sum())
    if weight_sum <= 0:
        return floor
    weight_values = weight_values / weight_sum

    corr_values = correlation.loc[names, names].to_numpy(dtype="float64")
    forecast_variance = float(weight_values @ corr_values @ weight_values)
    if forecast_variance <= 0 or np.isnan(forecast_variance):
        return cap

    multiplier = 1.0 / sqrt(forecast_variance)
    return max(floor, min(cap, multiplier))


def calculate_forecast_diversification_diagnostics(
    forecasts: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    *,
    min_periods: int = 20,
    floor: float = DEFAULT_FDM_FLOOR,
    cap: float = DEFAULT_FDM_CAP,
) -> ForecastDiversificationDiagnostics:
    """Calculate correlation, average correlation, and FDM for a forecast set."""
    correlation = calculate_forecast_correlation(forecasts, min_periods=min_periods)
    multiplier = calculate_forecast_diversification_multiplier(
        correlation,
        weights,
        floor=floor,
        cap=cap,
    )
    return ForecastDiversificationDiagnostics(
        multiplier=multiplier,
        correlation=correlation,
        average_correlation=calculate_average_correlation(correlation),
    )


def correlation_to_dict(correlation: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Convert a correlation matrix to a simple nested dict for result metadata."""
    return {
        str(row_name): {str(column_name): float(value) for column_name, value in row.items()}
        for row_name, row in correlation.iterrows()
    }
