"""Carver-style combined forecasts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from glebza.tradeapp.src.framework.forecasts.forecast_diversification import (
    calculate_forecast_diversification_diagnostics,
    correlation_to_dict,
)
from glebza.tradeapp.src.framework.forecasts.ewmac_forecast import (
    EWMACConfig,
    FORECAST_CAP,
    cap_forecast,
    ewmac_forecast_series,
)

DEFAULT_EWMAC_VARIATIONS = (
    EWMACConfig(fast_span=4, slow_span=16),
    EWMACConfig(fast_span=16, slow_span=64),
    EWMACConfig(fast_span=64, slow_span=256),
)


def combine_weighted_forecasts(
    components: Mapping[str, float],
    weights: Mapping[str, float],
    cap: float = FORECAST_CAP,
) -> float:
    """Linearly combine rule forecasts with weights, then cap the result."""
    total = 0.0
    for name, weight in weights.items():
        total += float(components.get(name, 0.0)) * float(weight)
    return max(-cap, min(cap, total))


def ewmac_variation_name(config: EWMACConfig) -> str:
    """Stable name for one EWMAC variation."""
    return f"ewmac_{config.fast_span}_{config.slow_span}"


def ewmac_forecast_batch(
    klines: pd.DataFrame,
    configs: Iterable[EWMACConfig] = DEFAULT_EWMAC_VARIATIONS,
) -> dict[str, pd.Series]:
    """Calculate one forecast series per EWMAC variation."""
    return {ewmac_variation_name(config): ewmac_forecast_series(klines, config) for config in configs}


def equal_weights(names: Iterable[str]) -> dict[str, float]:
    """Return equal weights for a non-empty set of forecast names."""
    names = list(names)
    if not names:
        raise ValueError("names must not be empty")
    weight = 1.0 / len(names)
    return {name: weight for name in names}


def combine_forecast_series(
    forecasts: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    cap: float = FORECAST_CAP,
    *,
    diversification_multiplier: float = 1.0,
) -> pd.Series:
    """Combine multiple forecast series with weights, then cap to Carver's range."""
    if not forecasts:
        raise ValueError("forecasts must not be empty")
    if diversification_multiplier <= 0:
        raise ValueError("diversification_multiplier must be positive")

    first = next(iter(forecasts.values()))
    total = pd.Series(0.0, index=first.index)
    for name, weight in weights.items():
        forecast = forecasts.get(name)
        if forecast is not None:
            total = total.add(forecast * float(weight), fill_value=0.0)

    return cap_forecast(total * diversification_multiplier, floor=-cap, cap=cap)


def combine_ewmac_and_carry_forecast_series(
    ewmac_forecast: pd.Series,
    carry_forecast: pd.Series,
    *,
    ewmac_weight: float = 0.5,
    carry_weight: float = 0.5,
    cap: float = FORECAST_CAP,
) -> pd.Series:
    """Combine the EWMAC forecast group with the carry forecast."""
    return combine_forecast_series(
        {
            "ewmac": ewmac_forecast,
            "carry": carry_forecast,
        },
        {
            "ewmac": ewmac_weight,
            "carry": carry_weight,
        },
        cap=cap,
    )


def attach_ewmac_forecast_columns(
    klines: pd.DataFrame,
    configs: Iterable[EWMACConfig] = DEFAULT_EWMAC_VARIATIONS,
    weights: Mapping[str, float] | None = None,
    cap: float = FORECAST_CAP,
    *,
    apply_fdm: bool = True,
) -> pd.DataFrame:
    """Add one column per EWMAC variation and a capped ``combined_forecast`` column."""
    rows = klines.copy()
    forecasts = ewmac_forecast_batch(rows, configs)
    resolved_weights = dict(weights or equal_weights(forecasts.keys()))
    diagnostics = calculate_forecast_diversification_diagnostics(forecasts, resolved_weights)
    multiplier = diagnostics.multiplier if apply_fdm else 1.0

    for name, series in forecasts.items():
        rows[f"forecast_{name}"] = series

    rows["combined_forecast_before_fdm"] = combine_forecast_series(
        forecasts,
        resolved_weights,
        cap=cap,
        diversification_multiplier=1.0,
    )
    rows["combined_forecast_fdm"] = multiplier
    rows["combined_forecast"] = combine_forecast_series(
        forecasts,
        resolved_weights,
        cap=cap,
        diversification_multiplier=multiplier,
    )
    rows.attrs["forecast_diversification_multiplier"] = multiplier
    rows.attrs["forecast_average_correlation"] = diagnostics.average_correlation
    rows.attrs["forecast_correlations"] = correlation_to_dict(diagnostics.correlation)
    return rows


def calculate_combined_ewmac_forecast_series(
    klines: pd.DataFrame,
    configs: Iterable[EWMACConfig] = DEFAULT_EWMAC_VARIATIONS,
    weights: Mapping[str, float] | None = None,
    cap: float = FORECAST_CAP,
) -> pd.Series:
    """Calculate and combine the default EWMAC variation batch."""
    return attach_ewmac_forecast_columns(klines, configs, weights, cap=cap)["combined_forecast"]
