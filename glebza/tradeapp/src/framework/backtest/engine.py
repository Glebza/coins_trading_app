"""Minimal Carver-style backtest skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Iterable, Optional

import pandas as pd

from glebza.tradeapp.src.framework import account as accounts
from glebza.tradeapp.src.framework import sizing, volatility
from glebza.tradeapp.src.framework.backtest.result import BacktestResult
from glebza.tradeapp.src.framework.forecasts import combined_forecast
from glebza.tradeapp.src.framework.forecasts.carry_forecast import add_carry_forecast_columns
from glebza.tradeapp.src.framework.forecasts.forecast_diversification import (
    ForecastDiversificationDiagnostics,
    calculate_forecast_diversification_diagnostics,
    correlation_to_dict,
)
from glebza.tradeapp.src.framework.risk import trailing_stop


@dataclass
class CompoundingBarState:
    """Mutable state for bar-by-bar compounding backtests and streaming replay."""

    equity: float = 1.0
    previous_position: float = 0.0
    previous_close: Optional[float] = None
    stop_state: trailing_stop.TrailingStopState = field(default_factory=trailing_stop.TrailingStopState)


@dataclass(frozen=True)
class CompoundingBarStep:
    """Outputs produced when processing one backtest bar."""

    capital_at_risk: float
    target_position: float
    position: float
    trade: float
    commission: float
    gross_strategy_return: float
    commission_return: float
    strategy_return: float
    equity: float
    price_change: float


def process_compounding_bar(
    state: CompoundingBarState,
    *,
    close: float,
    forecast: float,
    volatility_value: float,
    account: accounts.TradingAccount,
    initial_capital: float,
    periods_per_year: int,
    block_value: float,
    lot_size: int,
    short_enabled: bool,
    position_inertia: float,
    trailing_stop_multiplier: float,
) -> tuple[CompoundingBarState, CompoundingBarStep]:
    """Advance compounding backtest state by one bar."""
    capital_at_risk = initial_capital * state.equity
    price_change = 0.0 if state.previous_close is None else float(close) - float(state.previous_close)
    use_trailing_stop = trailing_stop_multiplier > 0
    stop_state = state.stop_state

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
    if not short_enabled:
        target = max(0.0, target)

    if use_trailing_stop:
        position = trailing_stop.apply_trailing_stop_inertia_step(
            state.previous_position,
            target,
            float(close),
            float(volatility_value),
            stop_state,
            multiplier=trailing_stop_multiplier,
            inertia_threshold=position_inertia,
        )
    else:
        position = sizing.apply_inertia_step(state.previous_position, target, threshold=position_inertia)

    position = sizing.cap_position_units(
        position,
        float(close),
        max_notional=max_notional,
        block_value=block_value,
        lot_size=lot_size,
    )
    if not short_enabled:
        position = max(0.0, position)

    trade = position - state.previous_position
    commission = abs(trade) * float(close) * block_value * account.commission_rate
    gross_return = (
        (state.previous_position * price_change * block_value / capital_at_risk) if capital_at_risk > 0 else 0.0
    )
    commission_return = commission / capital_at_risk if capital_at_risk > 0 else 0.0
    strategy_return = gross_return - commission_return
    equity = state.equity * (1.0 + strategy_return)

    next_state = CompoundingBarState(
        equity=equity,
        previous_position=position,
        previous_close=float(close),
        stop_state=stop_state,
    )
    step = CompoundingBarStep(
        capital_at_risk=capital_at_risk,
        target_position=target,
        position=position,
        trade=trade,
        commission=commission,
        gross_strategy_return=gross_return,
        commission_return=commission_return,
        strategy_return=strategy_return,
        equity=equity,
        price_change=price_change,
    )
    return next_state, step


def _run_compounding_backtest_rows(
    rows: pd.DataFrame,
    account: accounts.TradingAccount,
    *,
    periods_per_year: int,
    block_value: float,
    lot_size: int,
    short_enabled: bool,
    position_inertia: float,
    trailing_stop_multiplier: float,
) -> pd.DataFrame:
    """Simulate bar by bar with capital at risk = initial capital * equity."""
    initial_capital = float(account.trading_capital)
    state = CompoundingBarState()

    capital_at_risk_values: list[float] = []
    target_positions: list[float] = []
    positions: list[float] = []
    trades: list[float] = []
    gross_returns: list[float] = []
    commission_returns: list[float] = []
    strategy_returns: list[float] = []
    equities: list[float] = []
    commissions: list[float] = []
    price_changes: list[float] = []

    closes = pd.to_numeric(rows["close_price"]).astype("float64")
    forecasts = pd.to_numeric(rows["combined_forecast"]).astype("float64")
    volatilities = pd.to_numeric(rows["price_volatility"]).astype("float64")

    for close, forecast, volatility_value in zip(closes, forecasts, volatilities):
        state, step = process_compounding_bar(
            state,
            close=float(close),
            forecast=float(forecast),
            volatility_value=float(volatility_value),
            account=account,
            initial_capital=initial_capital,
            periods_per_year=periods_per_year,
            block_value=block_value,
            lot_size=lot_size,
            short_enabled=short_enabled,
            position_inertia=position_inertia,
            trailing_stop_multiplier=trailing_stop_multiplier,
        )
        capital_at_risk_values.append(step.capital_at_risk)
        target_positions.append(step.target_position)
        positions.append(step.position)
        trades.append(step.trade)
        commissions.append(step.commission)
        gross_returns.append(step.gross_strategy_return)
        commission_returns.append(step.commission_return)
        strategy_returns.append(step.strategy_return)
        equities.append(step.equity)
        price_changes.append(step.price_change)

    rows["capital_at_risk"] = capital_at_risk_values
    rows["target_position"] = target_positions
    rows["position"] = positions
    rows["trade"] = trades
    rows["commission"] = commissions
    rows["price_change"] = price_changes
    rows["gross_strategy_return"] = gross_returns
    rows["commission_return"] = commission_returns
    rows["strategy_return"] = strategy_returns
    rows["equity"] = equities
    rows["drawdown"] = (rows["equity"] / rows["equity"].cummax()) - 1.0
    return rows


def _apply_final_forecast_fdm(
    rows: pd.DataFrame,
    forecasts: dict[str, pd.Series],
    weights: dict[str, float],
    diagnostics: ForecastDiversificationDiagnostics | None = None,
) -> pd.DataFrame:
    diagnostics = diagnostics or calculate_forecast_diversification_diagnostics(forecasts, weights)
    rows["combined_forecast_before_fdm"] = combined_forecast.combine_forecast_series(
        forecasts,
        weights,
        diversification_multiplier=1.0,
    )
    rows["combined_forecast_fdm"] = diagnostics.multiplier
    rows["combined_forecast"] = combined_forecast.combine_forecast_series(
        forecasts,
        weights,
        diversification_multiplier=diagnostics.multiplier,
    )
    rows.attrs["forecast_diversification_multiplier"] = diagnostics.multiplier
    rows.attrs["forecast_average_correlation"] = diagnostics.average_correlation
    rows.attrs["forecast_correlations"] = correlation_to_dict(diagnostics.correlation)
    return rows


def _ewmac_forecast_components(rows: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        column.removeprefix("forecast_"): rows[column]
        for column in sorted(rows.columns)
        if column.startswith("forecast_ewmac_")
    }


def calculate_cagr(rows: pd.DataFrame, total_return: float) -> float:
    """Calculate CAGR from the first and last timestamps in result rows."""
    if "k_interval" in rows.columns:
        dates = pd.to_datetime(rows["k_interval"], utc=True)
    else:
        dates = pd.to_datetime(rows.index, utc=True)
    if len(dates) < 2:
        return total_return

    first_date = dates.iloc[0] if hasattr(dates, "iloc") else dates[0]
    last_date = dates.iloc[-1] if hasattr(dates, "iloc") else dates[-1]
    elapsed_days = (last_date - first_date).total_seconds() / 86_400
    years = elapsed_days / 365.25
    if years <= 0:
        return total_return
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def _build_final_forecast_components(
    rows: pd.DataFrame,
    dividends: Optional[Iterable[dict]],
    funding_rates: Optional[Iterable[dict]],
) -> tuple[pd.DataFrame, dict[str, pd.Series], dict[str, float]]:
    carry_funding_rates = list(funding_rates) if funding_rates is not None else []
    if carry_funding_rates:
        rows = add_carry_forecast_columns(
            rows,
            list(dividends or []),
            carry_funding_rates,
            rows["annualized_return_volatility"],
        )
        rows["combined_ewmac_forecast"] = rows["combined_forecast"]
        ewmac_components = _ewmac_forecast_components(rows)
        forecasts = {
            **ewmac_components,
            "carry": rows["forecast_carry"],
        }
        ewmac_weight = 0.5 / len(ewmac_components) if ewmac_components else 0.0
        weights = {
            **{name: ewmac_weight for name in ewmac_components},
            "carry": 0.5,
        }
        return rows, forecasts, weights

    forecasts = _ewmac_forecast_components(rows)
    return rows, forecasts, combined_forecast.equal_weights(forecasts.keys())


def calculate_single_instrument_forecast_diversification(
    klines: pd.DataFrame,
    *,
    dividends: Optional[Iterable[dict]] = None,
    funding_rates: Optional[Iterable[dict]] = None,
    periods_per_year: int = 252,
) -> ForecastDiversificationDiagnostics:
    """Calculate final forecast FDM from a calibration window without running P&L."""
    rows = klines.copy()
    if "k_interval" in rows.columns:
        rows = rows.sort_values("k_interval").reset_index(drop=True)

    rows["close_price"] = pd.to_numeric(rows["close_price"]).astype("float64")
    rows = combined_forecast.attach_ewmac_forecast_columns(rows, apply_fdm=False)
    rows["annualized_return_volatility"] = volatility.estimate_annualized_return_volatility(
        rows["close_price"],
        periods_per_year=periods_per_year,
    )
    _, forecasts, weights = _build_final_forecast_components(
        rows,
        dividends,
        funding_rates,
    )
    return calculate_forecast_diversification_diagnostics(forecasts, weights)


def run_single_instrument_backtest(
    klines: pd.DataFrame,
    *,
    account: accounts.TradingAccount | None = None,
    dividends: Optional[Iterable[dict]] = None,
    funding_rates: Optional[Iterable[dict]] = None,
    forecast_diversification_diagnostics: ForecastDiversificationDiagnostics | None = None,
    periods_per_year: int = 252,
    block_value: float = 1.0,
    lot_size: int = 1,
    short_enabled: bool = True,
    position_inertia: float = 0.10,
    trailing_stop_multiplier: float = 4.0,
) -> BacktestResult:
    """Backtest one instrument with the current combined EWMAC forecast."""
    if account is None:
        account = accounts.TradingAccount(trading_capital=100_000.0, annualized_volatility_target=0.35)

    rows = klines.copy()
    if "k_interval" in rows.columns:
        rows = rows.sort_values("k_interval").reset_index(drop=True)

    rows["close_price"] = pd.to_numeric(rows["close_price"]).astype("float64")
    rows = combined_forecast.attach_ewmac_forecast_columns(rows, apply_fdm=False)
    rows["price_volatility"] = volatility.estimate_daily_price_volatility(rows["close_price"])
    rows["annualized_return_volatility"] = volatility.estimate_annualized_return_volatility(
        rows["close_price"],
        periods_per_year=periods_per_year,
    )
    rows, final_forecasts, final_weights = _build_final_forecast_components(
        rows,
        dividends,
        funding_rates,
    )
    rows = _apply_final_forecast_fdm(
        rows,
        final_forecasts,
        final_weights,
        diagnostics=forecast_diversification_diagnostics,
    )
    rows["return"] = rows["close_price"].pct_change().fillna(0.0)
    rows["price_change"] = rows["close_price"].diff().fillna(0.0)

    rows = _run_compounding_backtest_rows(
        rows,
        account,
        periods_per_year=periods_per_year,
        block_value=block_value,
        lot_size=lot_size,
        short_enabled=short_enabled,
        position_inertia=position_inertia,
        trailing_stop_multiplier=trailing_stop_multiplier,
    )

    if "turnover" not in rows.columns:
        rows["turnover"] = rows["trade"].abs()

    total_return = float(rows["equity"].iloc[-1] - 1.0)
    cagr = calculate_cagr(rows, total_return)
    mean_return = float(rows["strategy_return"].mean())
    return_volatility = float(rows["strategy_return"].std(ddof=1))
    annualized_return = mean_return * periods_per_year
    annualized_volatility = return_volatility * sqrt(periods_per_year)
    sharpe = annualized_return / annualized_volatility if annualized_volatility else 0.0
    max_drawdown = float(rows["drawdown"].min())

    return BacktestResult(
        rows=rows,
        total_return=total_return,
        cagr=cagr,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        periods_per_year=periods_per_year,
        forecast_diversification_multiplier=float(rows.attrs.get("forecast_diversification_multiplier", 1.0)),
        forecast_average_correlation=rows.attrs.get("forecast_average_correlation"),
        forecast_correlations=rows.attrs.get("forecast_correlations"),
    )
