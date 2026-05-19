"""Minimal Carver-style backtest skeleton."""

from __future__ import annotations

from math import sqrt

import pandas as pd

from glebza.tradeapp.src.framework import account as accounts
from glebza.tradeapp.src.framework import sizing, volatility
from glebza.tradeapp.src.framework.backtest.result import BacktestResult
from glebza.tradeapp.src.framework.forecasts import combined_forecast
from glebza.tradeapp.src.framework.risk import trailing_stop


def _run_compounding_backtest_rows(
    rows: pd.DataFrame,
    account: accounts.TradingAccount,
    *,
    periods_per_year: int,
    block_value: float,
    lot_size: int,
    position_inertia: float,
    trailing_stop_multiplier: float,
) -> pd.DataFrame:
    """Simulate bar by bar with capital at risk = initial capital * equity."""
    initial_capital = float(account.trading_capital)
    equity = 1.0
    previous_position = 0.0
    stop_state = trailing_stop.TrailingStopState()
    use_trailing_stop = trailing_stop_multiplier > 0

    capital_at_risk_values: list[float] = []
    target_positions: list[float] = []
    positions: list[float] = []
    trades: list[float] = []
    gross_returns: list[float] = []
    commission_returns: list[float] = []
    strategy_returns: list[float] = []
    equities: list[float] = []

    closes = pd.to_numeric(rows["close_price"]).astype("float64")
    forecasts = pd.to_numeric(rows["combined_forecast"]).astype("float64")
    volatilities = pd.to_numeric(rows["price_volatility"]).astype("float64")
    price_changes = closes.diff().fillna(0.0)

    for close, forecast, volatility_value, price_change in zip(closes, forecasts, volatilities, price_changes):
        capital_at_risk = initial_capital * equity
        capital_at_risk_values.append(capital_at_risk)

        target = sizing.target_position_units(
            float(close),
            float(forecast),
            float(volatility_value),
            capital_at_risk,
            account,
            periods_per_year=periods_per_year,
            block_value=block_value,
            lot_size=lot_size,
        )
        max_notional = capital_at_risk * account.max_capital_multiple
        target = sizing.cap_position_units(
            target,
            float(close),
            max_notional=max_notional,
            block_value=block_value,
            lot_size=lot_size,
        )
        target_positions.append(target)

        if use_trailing_stop:
            position = trailing_stop.apply_trailing_stop_inertia_step(
                previous_position,
                target,
                float(close),
                float(volatility_value),
                stop_state,
                multiplier=trailing_stop_multiplier,
                inertia_threshold=position_inertia,
            )
        else:
            position = sizing.apply_inertia_step(previous_position, target, threshold=position_inertia)

        position = sizing.cap_position_units(
            position,
            float(close),
            max_notional=max_notional,
            block_value=block_value,
            lot_size=lot_size,
        )
        positions.append(position)

        trade = position - previous_position
        trades.append(trade)
        commission = abs(trade) * float(close) * block_value * account.commission_rate
        gross_return = (
            (previous_position * float(price_change) * block_value / capital_at_risk) if capital_at_risk > 0 else 0.0
        )
        commission_return = commission / capital_at_risk if capital_at_risk > 0 else 0.0
        strategy_return = gross_return - commission_return

        gross_returns.append(gross_return)
        commission_returns.append(commission_return)
        strategy_returns.append(strategy_return)

        equity *= 1.0 + strategy_return
        equities.append(equity)
        previous_position = position

    rows["capital_at_risk"] = capital_at_risk_values
    rows["target_position"] = target_positions
    rows["position"] = positions
    rows["trade"] = trades
    rows["commission"] = [
        abs(trade) * float(close) * block_value * account.commission_rate
        for trade, close in zip(trades, closes)
    ]
    rows["gross_strategy_return"] = gross_returns
    rows["commission_return"] = commission_returns
    rows["strategy_return"] = strategy_returns
    rows["equity"] = equities
    rows["drawdown"] = (rows["equity"] / rows["equity"].cummax()) - 1.0
    return rows


def run_single_instrument_backtest(
    klines: pd.DataFrame,
    *,
    account: accounts.TradingAccount | None = None,
    periods_per_year: int = 252,
    block_value: float = 1.0,
    lot_size: int = 1,
    position_inertia: float = 0.10,
    trailing_stop_multiplier: float = 4.0,
    compound_capital_at_risk: bool = True,
) -> BacktestResult:
    """Backtest one instrument with the current combined EWMAC forecast."""
    if account is None:
        account = accounts.TradingAccount(trading_capital=100_000.0, annualized_volatility_target=0.35)

    rows = klines.copy()
    if "k_interval" in rows.columns:
        rows = rows.sort_values("k_interval").reset_index(drop=True)

    rows["close_price"] = pd.to_numeric(rows["close_price"]).astype("float64")
    rows = combined_forecast.attach_ewmac_forecast_columns(rows)
    rows["price_volatility"] = volatility.estimate_daily_price_volatility(rows["close_price"])
    rows["return"] = rows["close_price"].pct_change().fillna(0.0)
    rows["price_change"] = rows["close_price"].diff().fillna(0.0)

    if compound_capital_at_risk:
        rows = _run_compounding_backtest_rows(
            rows,
            account,
            periods_per_year=periods_per_year,
            block_value=block_value,
            lot_size=lot_size,
            position_inertia=position_inertia,
            trailing_stop_multiplier=trailing_stop_multiplier,
        )
    else:
        rows["target_position"] = sizing.single_instrument_position_size(
            rows["close_price"],
            rows["combined_forecast"],
            rows["price_volatility"],
            account,
            periods_per_year=periods_per_year,
            block_value=block_value,
            lot_size=lot_size,
        ).fillna(0.0)
        rows["capital_at_risk"] = float(account.trading_capital)
        rows["target_position"] = sizing.cap_position_to_max_notional(
            rows["target_position"],
            rows["close_price"],
            max_notional=account.max_notional(),
            block_value=block_value,
            lot_size=lot_size,
        )
        if trailing_stop_multiplier > 0:
            rows["position"] = trailing_stop.apply_trailing_stop(
                rows["target_position"],
                rows["close_price"],
                rows["price_volatility"],
                multiplier=trailing_stop_multiplier,
                inertia_threshold=position_inertia,
            )
        else:
            rows["position"] = sizing.apply_position_inertia(rows["target_position"], threshold=position_inertia)
        rows["position"] = sizing.cap_position_to_max_notional(
            rows["position"],
            rows["close_price"],
            max_notional=account.max_notional(),
            block_value=block_value,
            lot_size=lot_size,
        )
        rows["trade"] = rows["position"].diff().fillna(rows["position"])
        rows["turnover"] = rows["trade"].abs()
        rows["commission"] = rows["turnover"] * rows["close_price"] * block_value * account.commission_rate
        rows["gross_strategy_return"] = (
            rows["position"].shift(1).fillna(0.0)
            * rows["price_change"]
            * block_value
            / float(account.trading_capital)
        ).fillna(0.0)
        rows["commission_return"] = rows["commission"] / float(account.trading_capital)
        rows["strategy_return"] = rows["gross_strategy_return"] - rows["commission_return"]
        rows["equity"] = (1.0 + rows["strategy_return"]).cumprod()
        rows["drawdown"] = (rows["equity"] / rows["equity"].cummax()) - 1.0

    if "turnover" not in rows.columns:
        rows["turnover"] = rows["trade"].abs()

    total_return = float(rows["equity"].iloc[-1] - 1.0)
    mean_return = float(rows["strategy_return"].mean())
    return_volatility = float(rows["strategy_return"].std(ddof=1))
    annualized_return = mean_return * periods_per_year
    annualized_volatility = return_volatility * sqrt(periods_per_year)
    sharpe = annualized_return / annualized_volatility if annualized_volatility else 0.0
    max_drawdown = float(rows["drawdown"].min())

    return BacktestResult(
        rows=rows,
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
    )
