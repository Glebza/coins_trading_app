"""Systematic trailing stop (Carver-style, volatility-based)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class TrailingStopState:
    peak: float | None = None
    trough: float | None = None
    block_long: bool = False
    block_short: bool = False


def apply_trailing_stop_inertia_step(
    current_position: float,
    target: float,
    close: float,
    volatility: float,
    state: TrailingStopState,
    *,
    multiplier: float,
    inertia_threshold: float,
) -> float:
    """Advance trailing stop and inertia by one bar. Returns the new position."""
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    if inertia_threshold < 0:
        raise ValueError("inertia_threshold must be non-negative")

    stop_distance = multiplier * float(volatility) if volatility > 0 and pd.notna(volatility) else float("inf")

    if current_position > 0:
        state.peak = close if state.peak is None else max(state.peak, close)
        if close <= state.peak - stop_distance:
            current_position = 0.0
            state.peak = None
            state.block_long = True
    elif current_position < 0:
        state.trough = close if state.trough is None else min(state.trough, close)
        if close >= state.trough + stop_distance:
            current_position = 0.0
            state.trough = None
            state.block_short = True

    raw_target = float(target)
    effective_target = raw_target
    if state.block_long and raw_target > 0:
        effective_target = 0.0
    if state.block_short and raw_target < 0:
        effective_target = 0.0
    if raw_target <= 0:
        state.block_long = False
    if raw_target >= 0:
        state.block_short = False

    difference = effective_target - current_position
    no_trade_zone = abs(effective_target) * inertia_threshold
    if abs(difference) > no_trade_zone:
        current_position = effective_target
        if current_position > 0:
            state.peak = close
            state.trough = None
        elif current_position < 0:
            state.trough = close
            state.peak = None
        else:
            state.peak = None
            state.trough = None

    return current_position


def apply_trailing_stop(
    target_position: pd.Series,
    close_price: pd.Series,
    price_volatility: pd.Series,
    *,
    multiplier: float = 4.0,
    inertia_threshold: float = 0.10,
) -> pd.Series:
    """Apply a trailing stop, then position inertia, bar by bar."""
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    if inertia_threshold < 0:
        raise ValueError("inertia_threshold must be non-negative")

    targets = pd.to_numeric(target_position).fillna(0.0)
    closes = pd.to_numeric(close_price).astype("float64")
    volatilities = pd.to_numeric(price_volatility).astype("float64")

    current_position = 0.0
    state = TrailingStopState()
    positions: list[float] = []

    for target, close, volatility in zip(targets, closes, volatilities):
        current_position = apply_trailing_stop_inertia_step(
            current_position,
            float(target),
            float(close),
            float(volatility),
            state,
            multiplier=multiplier,
            inertia_threshold=inertia_threshold,
        )
        positions.append(current_position)

    return pd.Series(positions, index=target_position.index)
