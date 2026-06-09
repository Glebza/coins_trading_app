"""Position sizing helpers."""

from __future__ import annotations

import pandas as pd

from glebza.tradeapp.src.framework.account import TradingAccount
from glebza.tradeapp.src.framework.volatility import daily_cash_volatility_target


def round_position_units(position: float, lot_size: int) -> float:
    """Round one position to the nearest tradable lot increment."""
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")
    return round(position / lot_size) * lot_size


def round_position_to_lot(position: pd.Series, lot_size: int) -> pd.Series:
    """Round position units to the nearest tradable lot increment."""
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")
    return (position / lot_size).round() * lot_size


def cap_position_to_max_notional(
    position: pd.Series,
    close_price: pd.Series,
    *,
    max_notional: float,
    block_value: float = 1.0,
    lot_size: int = 1,
) -> pd.Series:
    """Limit abs(position * close * block_value) to ``max_notional`` and re-round to lots."""

    close = pd.to_numeric(close_price).astype("float64")
    units = pd.to_numeric(position).astype("float64")
    unit_value = close * block_value
    notional = units * unit_value
    capped_notional = notional.clip(lower=-max_notional, upper=max_notional)
    capped_units = capped_notional / unit_value.where(unit_value > 0)
    capped_units = capped_units.fillna(0.0)
    return round_position_to_lot(capped_units, lot_size)


def cap_position_units(
    position: float,
    close: float,
    *,
    max_notional: float,
    block_value: float = 1.0,
    lot_size: int = 1,
) -> float:
    """Limit abs(position * close * block_value) to ``max_notional`` and re-round to lots."""
    if max_notional <= 0:
        raise ValueError("max_notional must be positive")
    if block_value <= 0:
        raise ValueError("block_value must be positive")

    unit_value = close * block_value
    if unit_value <= 0:
        return 0.0
    notional = position * unit_value
    capped_notional = max(-max_notional, min(max_notional, notional))
    return round_position_units(capped_notional / unit_value, lot_size)


def apply_inertia_step(current_position: float, target: float, *, threshold: float) -> float:
    """Keep current position unless target is far enough away."""
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    difference = target - current_position
    no_trade_zone = abs(target) * threshold
    if abs(difference) > no_trade_zone:
        return float(target)
    return current_position


def target_position_units(
    close: float,
    combined_forecast: float,
    price_volatility: float,
    capital_at_risk: float,
    account: TradingAccount,
    *,
    periods_per_year: int = 252,
    block_value: float = 1.0,
    lot_size: int = 1,
) -> float:
    """Size one instrument bar from forecast and current capital at risk."""
    if block_value <= 0:
        raise ValueError("block_value must be positive")
    if capital_at_risk <= 0:
        return 0.0
    if close <= 0:
        return 0.0

    daily_cash_target = daily_cash_volatility_target(account, periods_per_year=periods_per_year)
    daily_risk_pct = daily_cash_target / capital_at_risk
    if price_volatility <= 0 or pd.isna(price_volatility):
        return 0.0

    price_volatility_pct = price_volatility / close
    capital_pct = (combined_forecast / 10.0) * (daily_risk_pct / price_volatility_pct)
    raw_position = (capital_at_risk * capital_pct) / (close * block_value)
    return round_position_units(raw_position, lot_size)


def apply_position_inertia(target_position: pd.Series, *, threshold: float = 0.10) -> pd.Series:
    """Keep current position unless target is far enough away.

    ``threshold=0.10`` means: if current position is within 10% of the target,
    do not trade. This avoids small frequent adjusting trades.
    """

    if threshold < 0:
        raise ValueError("threshold must be non-negative")

    current_position = 0.0
    positions: list[float] = []
    for target in pd.to_numeric(target_position).fillna(0.0):
        current_position = apply_inertia_step(current_position, float(target), threshold=threshold)
        positions.append(current_position)
    return pd.Series(positions, index=target_position.index)


def single_instrument_position_size(
    close_price: pd.Series,
    combined_forecast: pd.Series,
    price_volatility: pd.Series,
    account: TradingAccount,
    *,
    periods_per_year: int = 252,
    block_value: float = 1.0,
    lot_size: int = 1,
) -> pd.Series:
    """Size one instrument from forecast strength and expected price volatility.

    The function first computes the desired percentage of trading capital, then
    converts that capital allocation into instrument units.
    """

    if block_value <= 0:
        raise ValueError("block_value must be positive")

    close = pd.to_numeric(close_price).astype("float64")
    forecast = pd.to_numeric(combined_forecast).astype("float64")
    volatility = pd.to_numeric(price_volatility).astype("float64")

    capital_at_risk = pd.Series(float(account.trading_capital), index=close.index)
    targets = [
        target_position_units(
            float(close.iloc[i]),
            float(forecast.iloc[i]),
            float(volatility.iloc[i]),
            float(capital_at_risk.iloc[i]),
            account,
            periods_per_year=periods_per_year,
            block_value=block_value,
            lot_size=lot_size,
        )
        for i in range(len(close))
    ]
    return pd.Series(targets, index=close.index)
