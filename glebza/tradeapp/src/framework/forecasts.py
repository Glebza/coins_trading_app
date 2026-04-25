"""Carver-style scaled forecasts: per-rule values combined with weights, then capped."""

from __future__ import annotations

from typing import Mapping

# Robert Carver uses a bounded forecast scale (typically ±20) before volatility targeting.
FORECAST_CAP = 20.0


def combine_weighted_forecasts(
    components: Mapping[str, float],
    weights: Mapping[str, float],
    cap: float = FORECAST_CAP,
) -> float:
    """
    Linear combination of rule-level forecasts, then capped to [-cap, cap].

    Each component should already be on a comparable scale (e.g. roughly ±10 per rule).
    Weights are usually non-negative and sum to 1; they express how much each rule
    contributes to the combined forecast.
    """
    total = 0.0
    for name, w in weights.items():
        total += float(components.get(name, 0.0)) * float(w)
    if cap <= 0:
        return total
    return max(-cap, min(cap, total))
