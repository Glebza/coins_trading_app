"""Streaming replay backtest: append bars one-by-one to a growing working dataset.

Reads all required rows from the database (or any source), then feeds them sequentially
through the same forecast and sizing logic used by the batch engine. FDM is frozen from
a training window, matching expanding OOS and live trading.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import sqrt
from typing import Any, Iterable, Mapping, Optional

import pandas as pd

from glebza.tradeapp.src.framework.account import TradingAccount
from glebza.tradeapp.src.framework.backtest.engine import (
    CompoundingBarState,
    _apply_final_forecast_fdm,
    _build_final_forecast_components,
    calculate_cagr,
    calculate_single_instrument_forecast_diversification,
    process_compounding_bar,
)
from glebza.tradeapp.src.framework.backtest.portfolio_engine import (
    _add_months,
    _aggregate_portfolio_backtest,
    _combine_stage_results,
    _create_backtest_run,
    _load_klines_dataframe,
)
from glebza.tradeapp.src.framework.backtest.result import BacktestResult, PortfolioBacktestResult
from glebza.tradeapp.src.framework.forecasts import combined_forecast
from glebza.tradeapp.src.framework.forecasts.forecast_diversification import (
    ForecastDiversificationDiagnostics,
    correlation_to_dict,
)
from glebza.tradeapp.src.framework import volatility
from glebza.tradeapp.src.framework.portfolio import Portfolio
from repository.backtest_repository import BacktestRepository
from repository.funding_rate_repository import FundingRateRepository
from repository.history_repository import HistoryRepository
from repository.instrument_dividend_repository import InstrumentDividendRepository


def _normalize_bar_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _prepare_klines_frame(klines: pd.DataFrame) -> pd.DataFrame:
    rows = klines.copy()
    if "k_interval" not in rows.columns:
        raise ValueError("klines must include k_interval")
    rows["k_interval"] = pd.to_datetime(rows["k_interval"], utc=True)
    rows["close_price"] = pd.to_numeric(rows["close_price"]).astype("float64")
    return rows.sort_values("k_interval").reset_index(drop=True)


def _resolve_frozen_fdm_diagnostics(
    *,
    training_klines: Optional[pd.DataFrame],
    all_klines: pd.DataFrame,
    dividends: Optional[Iterable[dict]],
    funding_rates: Optional[Iterable[dict]],
    periods_per_year: int,
    forecast_diversification_diagnostics: Optional[ForecastDiversificationDiagnostics],
) -> ForecastDiversificationDiagnostics:
    if forecast_diversification_diagnostics is not None:
        return forecast_diversification_diagnostics

    fit_source = training_klines if training_klines is not None else all_klines
    if fit_source.empty:
        raise ValueError("FDM training klines must not be empty")
    return calculate_single_instrument_forecast_diversification(
        fit_source,
        dividends=dividends,
        funding_rates=funding_rates,
        periods_per_year=periods_per_year,
    )


def _compute_indicator_rows(
    working_klines: pd.DataFrame,
    *,
    dividends: Optional[Iterable[dict]],
    funding_rates: Optional[Iterable[dict]],
    periods_per_year: int,
    frozen_fdm: ForecastDiversificationDiagnostics,
) -> pd.DataFrame:
    rows = combined_forecast.attach_ewmac_forecast_columns(working_klines, apply_fdm=False)
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
        diagnostics=frozen_fdm,
    )
    rows["return"] = rows["close_price"].pct_change().fillna(0.0)
    return rows


class InstrumentStreamingBacktest:
    """Incremental single-instrument replay with a growing working kline dataset."""

    def __init__(
        self,
        account: TradingAccount,
        *,
        dividends: Optional[Iterable[dict]] = None,
        funding_rates: Optional[Iterable[dict]] = None,
        frozen_fdm: ForecastDiversificationDiagnostics,
        periods_per_year: int = 252,
        block_value: float = 1.0,
        lot_size: int = 1,
        short_enabled: bool = True,
        position_inertia: float = 0.10,
        trailing_stop_multiplier: float = 4.0,
    ) -> None:
        self._account = account
        self._dividends = list(dividends or [])
        self._funding_rates = list(funding_rates or [])
        self._frozen_fdm = frozen_fdm
        self._periods_per_year = periods_per_year
        self._block_value = block_value
        self._lot_size = lot_size
        self._short_enabled = short_enabled
        self._position_inertia = position_inertia
        self._trailing_stop_multiplier = trailing_stop_multiplier
        self._initial_capital = float(account.trading_capital)
        self._working_records: list[dict[str, Any]] = []
        self._history: list[dict[str, Any]] = []
        self._compounding_state = CompoundingBarState()

    def append_bar(self, bar: Mapping[str, Any]) -> dict[str, Any]:
        """Append one kline, recompute indicators on the working set, and advance P&L."""
        if "k_interval" not in bar or "close_price" not in bar:
            raise ValueError("bar must include k_interval and close_price")

        record = dict(bar)
        record["k_interval"] = _normalize_bar_timestamp(record["k_interval"])
        record["close_price"] = float(record["close_price"])
        self._working_records.append(record)

        working_klines = pd.DataFrame(self._working_records)
        indicator_rows = _compute_indicator_rows(
            working_klines,
            dividends=self._dividends,
            funding_rates=self._funding_rates,
            periods_per_year=self._periods_per_year,
            frozen_fdm=self._frozen_fdm,
        )
        last = indicator_rows.iloc[-1]
        self._compounding_state, step = process_compounding_bar(
            self._compounding_state,
            close=float(last["close_price"]),
            forecast=float(last["combined_forecast"]),
            volatility_value=float(last["price_volatility"]),
            account=self._account,
            initial_capital=self._initial_capital,
            periods_per_year=self._periods_per_year,
            block_value=self._block_value,
            lot_size=self._lot_size,
            short_enabled=self._short_enabled,
            position_inertia=self._position_inertia,
            trailing_stop_multiplier=self._trailing_stop_multiplier,
        )

        row_record = last.to_dict()
        row_record.update(
            {
                "capital_at_risk": step.capital_at_risk,
                "target_position": step.target_position,
                "position": step.position,
                "trade": step.trade,
                "commission": step.commission,
                "gross_strategy_return": step.gross_strategy_return,
                "commission_return": step.commission_return,
                "strategy_return": step.strategy_return,
                "equity": step.equity,
                "price_change": step.price_change,
            }
        )
        self._history.append(row_record)
        return row_record

    def to_result(self) -> BacktestResult:
        if not self._history:
            raise ValueError("streaming backtest produced no bars")

        rows = pd.DataFrame(self._history)
        rows["k_interval"] = pd.to_datetime(rows["k_interval"], utc=True)
        rows = rows.sort_values("k_interval").reset_index(drop=True)
        rows["drawdown"] = (rows["equity"] / rows["equity"].cummax()) - 1.0
        if "turnover" not in rows.columns:
            rows["turnover"] = rows["trade"].abs()

        total_return = float(rows["equity"].iloc[-1] - 1.0)
        cagr = calculate_cagr(rows, total_return)
        mean_return = float(rows["strategy_return"].mean())
        return_volatility = float(rows["strategy_return"].std(ddof=1))
        if pd.isna(return_volatility):
            return_volatility = 0.0
        annualized_return = mean_return * self._periods_per_year
        annualized_volatility = return_volatility * sqrt(self._periods_per_year)
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
            periods_per_year=self._periods_per_year,
            forecast_diversification_multiplier=float(self._frozen_fdm.multiplier),
            forecast_average_correlation=self._frozen_fdm.average_correlation,
            forecast_correlations=correlation_to_dict(self._frozen_fdm.correlation),
        )


def iter_kline_bars(klines: pd.DataFrame) -> Iterable[dict[str, Any]]:
    """Yield kline rows in chronological order."""
    frame = _prepare_klines_frame(klines)
    for row in frame.to_dict(orient="records"):
        yield row


def run_streaming_single_instrument_backtest(
    klines: pd.DataFrame,
    *,
    account: TradingAccount | None = None,
    training_klines: Optional[pd.DataFrame] = None,
    dividends: Optional[Iterable[dict]] = None,
    funding_rates: Optional[Iterable[dict]] = None,
    forecast_diversification_diagnostics: Optional[ForecastDiversificationDiagnostics] = None,
    periods_per_year: int = 252,
    block_value: float = 1.0,
    lot_size: int = 1,
    short_enabled: bool = True,
    position_inertia: float = 0.10,
    trailing_stop_multiplier: float = 4.0,
) -> BacktestResult:
    """Replay klines one bar at a time using a growing working dataset and frozen FDM."""
    if account is None:
        account = TradingAccount(trading_capital=100_000.0, annualized_volatility_target=0.35)

    prepared = _prepare_klines_frame(klines)
    if prepared.empty:
        raise ValueError("klines must not be empty")

    frozen_fdm = _resolve_frozen_fdm_diagnostics(
        training_klines=training_klines,
        all_klines=prepared,
        dividends=dividends,
        funding_rates=funding_rates,
        periods_per_year=periods_per_year,
        forecast_diversification_diagnostics=forecast_diversification_diagnostics,
    )
    replay = InstrumentStreamingBacktest(
        account,
        dividends=dividends,
        funding_rates=funding_rates,
        frozen_fdm=frozen_fdm,
        periods_per_year=periods_per_year,
        block_value=block_value,
        lot_size=lot_size,
        short_enabled=short_enabled,
        position_inertia=position_inertia,
        trailing_stop_multiplier=trailing_stop_multiplier,
    )
    for bar in iter_kline_bars(prepared):
        replay.append_bar(bar)
    return replay.to_result()


def _portfolio_replay_timestamps(klines_by_ticker: Mapping[str, pd.DataFrame]) -> list[pd.Timestamp]:
    timestamp_sets = [
        set(pd.to_datetime(frame["k_interval"], utc=True)) for frame in klines_by_ticker.values()
    ]
    if not timestamp_sets:
        return []
    common = timestamp_sets[0]
    for timestamps in timestamp_sets[1:]:
        common &= timestamps
    return sorted(common)


def _slice_klines_window(klines: pd.DataFrame, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    frame = _prepare_klines_frame(klines)
    start = _normalize_bar_timestamp(start_dt)
    end = _normalize_bar_timestamp(end_dt)
    filtered = frame[(frame["k_interval"] >= start) & (frame["k_interval"] < end)]
    return filtered.reset_index(drop=True)


def run_streaming_oos_stages_for_klines(
    klines: pd.DataFrame,
    *,
    account: TradingAccount,
    start_dt: datetime,
    end_dt: datetime,
    step_months: int,
    dividends: Optional[Iterable[dict]] = None,
    funding_rates: Optional[Iterable[dict]] = None,
    periods_per_year: int = 252,
    block_value: float = 1.0,
    lot_size: int = 1,
    short_enabled: bool = True,
    position_inertia: float = 0.10,
    trailing_stop_multiplier: float = 4.0,
) -> BacktestResult:
    """Expanding OOS via streaming replay: fit FDM on each training window, stream the test step."""
    if step_months <= 0:
        raise ValueError("step_months must be positive")

    first_test_start = _add_months(start_dt, step_months)
    if first_test_start >= end_dt:
        raise ValueError("OOS requires at least one training step before the test window")

    stage_results: list[BacktestResult] = []
    stage = 1
    test_start = first_test_start
    while test_start < end_dt:
        test_end = min(_add_months(test_start, step_months), end_dt)
        training_klines = _slice_klines_window(klines, start_dt, test_start)
        test_klines = _slice_klines_window(klines, test_start, test_end)
        if training_klines.empty or test_klines.empty:
            raise ValueError(
                f"OOS stage {stage} has no klines in training [{start_dt}, {test_start}) "
                f"or test [{test_start}, {test_end})"
            )

        frozen_fdm = calculate_single_instrument_forecast_diversification(
            training_klines,
            dividends=dividends,
            funding_rates=funding_rates,
            periods_per_year=periods_per_year,
        )
        replay = InstrumentStreamingBacktest(
            account,
            dividends=dividends,
            funding_rates=funding_rates,
            frozen_fdm=frozen_fdm,
            periods_per_year=periods_per_year,
            block_value=block_value,
            lot_size=lot_size,
            short_enabled=short_enabled,
            position_inertia=position_inertia,
            trailing_stop_multiplier=trailing_stop_multiplier,
        )
        for bar in iter_kline_bars(test_klines):
            replay.append_bar(bar)

        stage_result = replay.to_result()
        stage_result.rows["oos_stage"] = stage
        stage_result.rows["train_start_dt"] = start_dt
        stage_result.rows["train_end_dt"] = test_start
        stage_result.rows["test_start_dt"] = test_start
        stage_result.rows["test_end_dt"] = test_end
        stage_results.append(stage_result)
        test_start = test_end
        stage += 1

    return _combine_stage_results(stage_results, periods_per_year=periods_per_year)


def _run_streaming_expanding_oos_instrument_backtests(
    portfolio: Portfolio,
    account: TradingAccount,
    *,
    history_repository: HistoryRepository,
    dividend_repository: InstrumentDividendRepository,
    funding_rate_repository: FundingRateRepository,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    step_months: int,
    periods_per_year: int,
    position_inertia: float,
    trailing_stop_multiplier: float,
) -> dict[str, BacktestResult]:
    funding_rates = funding_rate_repository.list_funding_rates(end_dt=end_dt)
    results: dict[str, BacktestResult] = {}

    for instrument in portfolio.instruments:
        full_klines = _load_klines_dataframe(
            history_repository,
            instrument.instrument_id,
            interval,
            start_dt,
            end_dt,
            ticker=instrument.ticker,
        )
        dividends = dividend_repository.list_dividends(
            instrument.instrument_id,
            start_dt=start_dt - timedelta(days=365),
            end_dt=end_dt,
        )
        results[instrument.ticker] = run_streaming_oos_stages_for_klines(
            full_klines,
            account=account.allocate_capital(instrument.weight),
            start_dt=start_dt,
            end_dt=end_dt,
            step_months=step_months,
            dividends=dividends,
            funding_rates=funding_rates,
            periods_per_year=periods_per_year,
            block_value=instrument.block_value,
            lot_size=instrument.lot_size,
            short_enabled=instrument.short_enabled,
            position_inertia=position_inertia,
            trailing_stop_multiplier=trailing_stop_multiplier,
        )

    return results


def run_streaming_expanding_oos_portfolio_backtest(
    portfolio: Portfolio,
    account: TradingAccount,
    *,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    step_months: int,
    periods_per_year: int = 252,
    position_inertia: float = 0.10,
    trailing_stop_multiplier: float = 4.0,
    exchange: Mapping[str, Any],
    strategy_id: Optional[int] = None,
    backtest_repository: BacktestRepository | None = None,
    history_repository: HistoryRepository | None = None,
    dividend_repository: InstrumentDividendRepository | None = None,
    funding_rate_repository: FundingRateRepository | None = None,
) -> PortfolioBacktestResult:
    """Expanding OOS portfolio backtest with per-stage FDM fit and streaming test replay."""
    if step_months <= 0:
        raise ValueError("step_months must be positive")

    first_test_start = _add_months(start_dt, step_months)
    if first_test_start >= end_dt:
        raise ValueError("OOS requires at least one training step before the test window")

    backtest_repo = backtest_repository or BacktestRepository()
    resolved_strategy_id = strategy_id or backtest_repo.get_first_carver_strategy_id()
    run_id = _create_backtest_run(
        backtest_repo,
        portfolio,
        account,
        interval=interval,
        start_dt=start_dt,
        end_dt=end_dt,
        periods_per_year=periods_per_year,
        strategy_id=resolved_strategy_id,
        exchange=exchange,
        backtest_mode="streaming_expanding_oos",
        step_months=step_months,
    )

    try:
        history_repo = history_repository or HistoryRepository()
        dividend_repo = dividend_repository or InstrumentDividendRepository()
        funding_repo = funding_rate_repository or FundingRateRepository()
        instrument_results = _run_streaming_expanding_oos_instrument_backtests(
            portfolio,
            account,
            history_repository=history_repo,
            dividend_repository=dividend_repo,
            funding_rate_repository=funding_repo,
            interval=interval,
            start_dt=start_dt,
            end_dt=end_dt,
            step_months=step_months,
            periods_per_year=periods_per_year,
            position_inertia=position_inertia,
            trailing_stop_multiplier=trailing_stop_multiplier,
        )
        result = _aggregate_portfolio_backtest(
            instrument_results,
            portfolio,
            periods_per_year=periods_per_year,
            run_id=run_id,
        )
        ticker_to_id = {item.ticker: item.instrument_id for item in portfolio.instruments}
        backtest_repo.save_portfolio_run_result(
            run_id,
            result,
            ticker_to_instrument_id=ticker_to_id,
        )
        return result
    except Exception as exc:
        backtest_repo.fail_run(run_id, str(exc))
        raise


def run_streaming_portfolio_backtest(
    portfolio: Portfolio,
    account: TradingAccount,
    *,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    training_end_dt: Optional[datetime] = None,
    periods_per_year: int = 252,
    position_inertia: float = 0.10,
    trailing_stop_multiplier: float = 4.0,
    exchange: Mapping[str, Any],
    strategy_id: Optional[int] = None,
    backtest_repository: BacktestRepository | None = None,
    history_repository: HistoryRepository | None = None,
    dividend_repository: InstrumentDividendRepository | None = None,
    funding_rate_repository: FundingRateRepository | None = None,
) -> PortfolioBacktestResult:
    """Portfolio replay with per-instrument streaming states and frozen training-window FDM."""
    history_repo = history_repository or HistoryRepository()
    dividend_repo = dividend_repository or InstrumentDividendRepository()
    funding_repo = funding_rate_repository or FundingRateRepository()
    funding_rates = funding_repo.list_funding_rates(end_dt=end_dt)

    replay_states: dict[str, InstrumentStreamingBacktest] = {}
    klines_by_ticker: dict[str, pd.DataFrame] = {}

    for instrument in portfolio.instruments:
        full_klines = _load_klines_dataframe(
            history_repo,
            instrument.instrument_id,
            interval,
            start_dt,
            end_dt,
            ticker=instrument.ticker,
        )
        klines_by_ticker[instrument.ticker] = full_klines

        training_klines = None
        if training_end_dt is not None:
            training_klines = _load_klines_dataframe(
                history_repo,
                instrument.instrument_id,
                interval,
                start_dt,
                training_end_dt,
                ticker=instrument.ticker,
            )

        dividends = dividend_repo.list_dividends(
            instrument.instrument_id,
            start_dt=start_dt - timedelta(days=365),
            end_dt=end_dt,
        )
        frozen_fdm = _resolve_frozen_fdm_diagnostics(
            training_klines=training_klines,
            all_klines=full_klines,
            dividends=dividends,
            funding_rates=funding_rates,
            periods_per_year=periods_per_year,
            forecast_diversification_diagnostics=None,
        )
        replay_states[instrument.ticker] = InstrumentStreamingBacktest(
            account.allocate_capital(instrument.weight),
            dividends=dividends,
            funding_rates=funding_rates,
            frozen_fdm=frozen_fdm,
            periods_per_year=periods_per_year,
            block_value=instrument.block_value,
            lot_size=instrument.lot_size,
            short_enabled=instrument.short_enabled,
            position_inertia=position_inertia,
            trailing_stop_multiplier=trailing_stop_multiplier,
        )

    replay_start = training_end_dt or start_dt
    indexed_klines = {
        ticker: frame.set_index(pd.to_datetime(frame["k_interval"], utc=True))
        for ticker, frame in klines_by_ticker.items()
    }

    for timestamp in _portfolio_replay_timestamps(klines_by_ticker):
        if timestamp < _normalize_bar_timestamp(replay_start):
            continue
        for instrument in portfolio.instruments:
            bar_row = indexed_klines[instrument.ticker].loc[timestamp]
            if isinstance(bar_row, pd.DataFrame):
                bar_row = bar_row.iloc[0]
            bar = bar_row.to_dict()
            bar["k_interval"] = timestamp
            replay_states[instrument.ticker].append_bar(bar)

    instrument_results = {
        ticker: state.to_result() for ticker, state in replay_states.items()
    }

    backtest_repo = backtest_repository or BacktestRepository()
    resolved_strategy_id = strategy_id or backtest_repo.get_first_carver_strategy_id()
    backtest_mode = "streaming_replay" if training_end_dt is None else "streaming_replay_oos"
    run_id = _create_backtest_run(
        backtest_repo,
        portfolio,
        account,
        interval=interval,
        start_dt=start_dt,
        end_dt=end_dt,
        periods_per_year=periods_per_year,
        strategy_id=resolved_strategy_id,
        exchange=exchange,
        backtest_mode=backtest_mode,
    )

    try:
        result = _aggregate_portfolio_backtest(
            instrument_results,
            portfolio,
            periods_per_year=periods_per_year,
            run_id=run_id,
        )
        ticker_to_id = {item.ticker: item.instrument_id for item in portfolio.instruments}
        backtest_repo.save_portfolio_run_result(
            run_id,
            result,
            ticker_to_instrument_id=ticker_to_id,
        )
        return result
    except Exception as exc:
        backtest_repo.fail_run(run_id, str(exc))
        raise
