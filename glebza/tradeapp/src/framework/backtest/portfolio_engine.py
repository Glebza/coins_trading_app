"""Portfolio backtest orchestration and aggregation."""

from __future__ import annotations
import calendar
import logging
from datetime import datetime, timedelta
from math import sqrt
from typing import Any, Mapping, Optional
from glebza.tradeapp.src.framework.account import TradingAccount
from glebza.tradeapp.src.framework.backtest.engine import (
    calculate_cagr,
    calculate_single_instrument_forecast_diversification,
    run_single_instrument_backtest,
)
from glebza.tradeapp.src.framework.backtest.result import BacktestResult, PortfolioBacktestResult
from glebza.tradeapp.src.framework.forecasts.forecast_diversification import (
    calculate_average_correlation,
    correlation_to_dict,
)
from glebza.tradeapp.src.framework.portfolio import Portfolio
from repository.backtest_repository import BacktestRepository
from repository.history_repository import HistoryRepository
from repository.funding_rate_repository import FundingRateRepository
from repository.instrument_dividend_repository import InstrumentDividendRepository
import pandas as pd

logger = logging.getLogger(__name__)


def run_weighted_portfolio_backtest(
    portfolio: Portfolio,
    account: TradingAccount,
    *,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    instrument_results: Mapping[str, BacktestResult] | None = None,
    periods_per_year: int = 252,
    position_inertia: float = 0.10,
    trailing_stop_multiplier: float = 4.0,
    exchange: Mapping[str, Any],
    strategy_id: Optional[int] = None,
    backtest_repository: BacktestRepository | None = None,
) -> PortfolioBacktestResult:
    """Run a fixed-weight portfolio backtest and persist ``backtest_runs``.

    When ``instrument_results`` is omitted, loads klines and runs each sleeve.
    ``portfolio.id`` must already exist in the backtests schema.
    """
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
        backtest_mode="in_sample",
    )

    try:
        if instrument_results is None:
            history_repository = HistoryRepository()
            dividend_repository = InstrumentDividendRepository()
            funding_rate_repository = FundingRateRepository()
            instrument_results = _run_portfolio_instrument_backtests(
                portfolio,
                account,
                history_repository=history_repository,
                dividend_repository=dividend_repository,
                funding_rate_repository=funding_rate_repository,
                interval=interval,
                start_dt=start_dt,
                end_dt=end_dt,
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


def run_expanding_oos_portfolio_backtest(
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
) -> PortfolioBacktestResult:
    """Run expanding-window OOS: fit FDM on the past, test the next step."""
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
        backtest_mode="expanding_oos",
        step_months=step_months,
    )

    try:
        history_repository = HistoryRepository()
        dividend_repository = InstrumentDividendRepository()
        funding_rate_repository = FundingRateRepository()
        instrument_results = _run_expanding_oos_instrument_backtests(
            portfolio,
            account,
            history_repository=history_repository,
            dividend_repository=dividend_repository,
            funding_rate_repository=funding_rate_repository,
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


def _create_backtest_run(
    backtest_repo: BacktestRepository,
    portfolio: Portfolio,
    account: TradingAccount,
    *,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    periods_per_year: int,
    strategy_id: int,
    exchange: Mapping[str, Any],
    backtest_mode: str = "in_sample",
    step_months: Optional[int] = None,
) -> int:
    if portfolio.id is None:
        raise ValueError("portfolio.id is required — store the portfolio before launching")

    return backtest_repo.store_run_start_for_portfolio_backtest(
        portfolio_id=portfolio.id,
        exchange=exchange,
        strategy_id=strategy_id,
        kline_interval=interval,
        start_dt=start_dt,
        end_dt=end_dt,
        account=account,
        periods_per_year=periods_per_year,
        backtest_mode=backtest_mode,
        step_months=step_months,
    )


def _run_portfolio_instrument_backtests(
    portfolio: Portfolio,
    account: TradingAccount,
    *,
    history_repository: HistoryRepository,
    dividend_repository: InstrumentDividendRepository,
    funding_rate_repository: FundingRateRepository,
    interval: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    periods_per_year: int,
    position_inertia: float,
    trailing_stop_multiplier: float,
) -> dict[str, BacktestResult]:
    results: dict[str, BacktestResult] = {}
    funding_rates = funding_rate_repository.list_funding_rates(end_dt=end_dt)
    for instrument in portfolio.instruments:
        klines = pd.DataFrame(
            history_repository.get_klines_by_instrument(
                instrument.instrument_id,
                interval,
                start_dt,
                end_dt,
            )
        )
        if klines.empty:
            logger.warning(
                "dropped ticker=%s: no klines in [%s, %s] interval=%s",
                instrument.ticker,
                start_dt,
                end_dt,
                interval,
            )
            continue
        dividend_start_dt = start_dt - timedelta(days=365) if start_dt is not None else None
        dividends = dividend_repository.list_dividends(
            instrument.instrument_id,
            start_dt=dividend_start_dt,
            end_dt=end_dt,
        )
        results[instrument.ticker] = run_single_instrument_backtest(
            klines,
            account=account.allocate_capital(instrument.weight),
            dividends=dividends,
            funding_rates=funding_rates,
            periods_per_year=periods_per_year,
            block_value=instrument.block_value,
            lot_size=instrument.lot_size,
            short_enabled=instrument.short_enabled,
            position_inertia=position_inertia,
            trailing_stop_multiplier=trailing_stop_multiplier,
        )
    if not results:
        raise ValueError("no instruments produced backtest results after dropping tickers with missing klines")
    return results


def _run_expanding_oos_instrument_backtests(
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
    stage_results_by_ticker: dict[str, list[BacktestResult]] = {
        instrument.ticker: [] for instrument in portfolio.instruments
    }

    stage = 1
    test_start = _add_months(start_dt, step_months)
    while test_start < end_dt:
        test_end = min(_add_months(test_start, step_months), end_dt)
        for instrument in portfolio.instruments:
            dividends = dividend_repository.list_dividends(
                instrument.instrument_id,
                start_dt=start_dt - timedelta(days=365),
                end_dt=test_end,
            )
            training_klines = _try_load_klines_dataframe(
                history_repository,
                instrument.instrument_id,
                interval,
                start_dt,
                test_start,
                ticker=instrument.ticker,
            )
            test_klines = _try_load_klines_dataframe(
                history_repository,
                instrument.instrument_id,
                interval,
                test_start,
                test_end,
                ticker=instrument.ticker,
            )
            if training_klines is None or test_klines is None:
                logger.warning(
                    "skip oos stage=%s ticker=%s interval=%s "
                    "(training_window=[%s, %s) test_window=[%s, %s))",
                    stage,
                    instrument.ticker,
                    interval,
                    start_dt,
                    test_start,
                    test_start,
                    test_end,
                )
                continue
            diagnostics = calculate_single_instrument_forecast_diversification(
                training_klines,
                dividends=dividends,
                funding_rates=funding_rates,
                periods_per_year=periods_per_year,
            )
            stage_result = run_single_instrument_backtest(
                test_klines,
                account=account.allocate_capital(instrument.weight),
                dividends=dividends,
                funding_rates=funding_rates,
                forecast_diversification_diagnostics=diagnostics,
                periods_per_year=periods_per_year,
                block_value=instrument.block_value,
                lot_size=instrument.lot_size,
                short_enabled=instrument.short_enabled,
                position_inertia=position_inertia,
                trailing_stop_multiplier=trailing_stop_multiplier,
            )
            stage_result.rows["oos_stage"] = stage
            stage_result.rows["train_start_dt"] = start_dt
            stage_result.rows["train_end_dt"] = test_start
            stage_result.rows["test_start_dt"] = test_start
            stage_result.rows["test_end_dt"] = test_end
            stage_results_by_ticker[instrument.ticker].append(stage_result)
        test_start = test_end
        stage += 1

    combined: dict[str, BacktestResult] = {}
    for ticker, results in stage_results_by_ticker.items():
        if not results:
            logger.warning("dropped ticker=%s: no oos stage results after skipping missing klines", ticker)
            continue
        combined[ticker] = _combine_stage_results(results, periods_per_year=periods_per_year)
    if not combined:
        raise ValueError("no instruments produced oos results after dropping tickers with missing klines")
    return combined


def _try_load_klines_dataframe(
    history_repository: HistoryRepository,
    instrument_id: int,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    *,
    ticker: str,
) -> Optional[pd.DataFrame]:
    klines = pd.DataFrame(
        history_repository.get_klines_by_instrument(
            instrument_id,
            interval,
            start_dt,
            end_dt,
        )
    )
    if klines.empty:
        return None
    klines["k_interval"] = pd.to_datetime(klines["k_interval"], utc=True)
    filtered = klines[
        (klines["k_interval"] >= pd.Timestamp(start_dt))
        & (klines["k_interval"] < pd.Timestamp(end_dt))
    ]
    if filtered.empty:
        return None
    return filtered


def _load_klines_dataframe(
    history_repository: HistoryRepository,
    instrument_id: int,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    *,
    ticker: str,
) -> pd.DataFrame:
    loaded = _try_load_klines_dataframe(
        history_repository,
        instrument_id,
        interval,
        start_dt,
        end_dt,
        ticker=ticker,
    )
    if loaded is None:
        raise ValueError(
            f"No stored klines found for ticker='{ticker}' interval='{interval}' "
            f"in half-open window [{start_dt}, {end_dt})."
        )
    return loaded


def _combine_stage_results(results: list[BacktestResult], *, periods_per_year: int) -> BacktestResult:
    if not results:
        raise ValueError("OOS produced no stage results")

    rows = pd.concat([result.rows for result in results], axis=0).sort_values("k_interval").reset_index(drop=True)
    rows["equity"] = (1.0 + rows["strategy_return"]).cumprod()
    rows["drawdown"] = (rows["equity"] / rows["equity"].cummax()) - 1.0

    total_return = float(rows["equity"].iloc[-1] - 1.0)
    cagr = calculate_cagr(rows, total_return)
    mean_return = float(rows["strategy_return"].mean())
    return_volatility = float(rows["strategy_return"].std(ddof=1))
    if pd.isna(return_volatility):
        return_volatility = 0.0

    annualized_return = mean_return * periods_per_year
    annualized_volatility = return_volatility * sqrt(periods_per_year)
    sharpe = annualized_return / annualized_volatility if annualized_volatility else 0.0
    max_drawdown = float(rows["drawdown"].min())
    fdm = float(sum(result.forecast_diversification_multiplier for result in results) / len(results))
    correlations = _aggregate_forecast_diagnostics({str(index): result for index, result in enumerate(results)})

    return BacktestResult(
        rows=rows,
        total_return=total_return,
        cagr=cagr,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        periods_per_year=periods_per_year,
        forecast_diversification_multiplier=fdm,
        forecast_average_correlation=correlations[1],
        forecast_correlations=correlations[2],
    )


def _add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _aggregate_portfolio_backtest(
    instrument_results: Mapping[str, BacktestResult],
    portfolio: Portfolio,
    *,
    periods_per_year: int,
    run_id: Optional[int] = None,
) -> PortfolioBacktestResult:
    """Combine per-instrument backtests into portfolio-level returns and metrics."""
    active_instruments = [
        instrument for instrument in portfolio.instruments if instrument.ticker in instrument_results
    ]
    dropped = [
        instrument.ticker
        for instrument in portfolio.instruments
        if instrument.ticker not in instrument_results
    ]
    if dropped:
        logger.warning(
            "portfolio excludes tickers with missing backtest results: %s",
            ",".join(sorted(dropped)),
        )
    if not active_instruments:
        raise ValueError("no instruments left for portfolio aggregation after dropping missing tickers")

    weight_total = sum(instrument.weight for instrument in active_instruments)
    if weight_total <= 0:
        raise ValueError("active portfolio weights must sum to a positive value")

    return_columns: list[pd.Series] = []
    for instrument in active_instruments:
        normalized_weight = instrument.weight / weight_total
        rows = instrument_results[instrument.ticker].rows
        if "strategy_return" not in rows.columns:
            raise ValueError(f"strategy_return column is missing for ticker '{instrument.ticker}'")

        if "k_interval" in rows.columns:
            series = rows.set_index("k_interval")["strategy_return"]
        else:
            series = rows["strategy_return"]
        return_columns.append(pd.to_numeric(series).rename(instrument.ticker))

    returns = pd.concat(return_columns, axis=1, join="inner").sort_index()
    if returns.empty:
        raise ValueError("no overlapping return rows for portfolio instruments")

    result_rows = returns.copy()
    for instrument in active_instruments:
        normalized_weight = instrument.weight / weight_total
        result_rows[f"{instrument.ticker}_weighted_return"] = (
            result_rows[instrument.ticker] * normalized_weight
        )

    weighted_columns = [f"{instrument.ticker}_weighted_return" for instrument in active_instruments]
    result_rows["portfolio_return"] = result_rows[weighted_columns].sum(axis=1)
    result_rows = _attach_oos_metadata(result_rows, instrument_results, portfolio)
    result_rows["equity"] = (1.0 + result_rows["portfolio_return"]).cumprod()
    result_rows["drawdown"] = (result_rows["equity"] / result_rows["equity"].cummax()) - 1.0

    total_return = float(result_rows["equity"].iloc[-1] - 1.0)
    cagr = calculate_cagr(result_rows, total_return)
    mean_return = float(result_rows["portfolio_return"].mean())
    return_volatility = float(result_rows["portfolio_return"].std(ddof=1))
    if pd.isna(return_volatility):
        return_volatility = 0.0

    annualized_return = mean_return * periods_per_year
    annualized_volatility = return_volatility * sqrt(periods_per_year)
    sharpe = annualized_return / annualized_volatility if annualized_volatility else 0.0
    max_drawdown = float(result_rows["drawdown"].min())
    forecast_fdm, forecast_average_correlation, forecast_correlations = _aggregate_forecast_diagnostics(
        instrument_results
    )

    return PortfolioBacktestResult(
        rows=result_rows,
        instrument_results={
            instrument.ticker: instrument_results[instrument.ticker] for instrument in active_instruments
        },
        total_return=total_return,
        cagr=cagr,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        run_id=run_id,
        periods_per_year=periods_per_year,
        forecast_diversification_multiplier=forecast_fdm,
        forecast_average_correlation=forecast_average_correlation,
        forecast_correlations=forecast_correlations,
    )


def _attach_oos_metadata(
    result_rows: pd.DataFrame,
    instrument_results: Mapping[str, BacktestResult],
    portfolio: Portfolio,
) -> pd.DataFrame:
    metadata_columns = ["oos_stage", "train_start_dt", "train_end_dt", "test_start_dt", "test_end_dt"]
    for ticker in instrument_results:
        rows = instrument_results[ticker].rows
        if not set(metadata_columns).issubset(rows.columns):
            continue

        indexed = rows.set_index("k_interval") if "k_interval" in rows.columns else rows
        metadata = indexed[metadata_columns].reindex(result_rows.index)
        for column in metadata_columns:
            result_rows[column] = metadata[column]
        return result_rows
    return result_rows


def _aggregate_forecast_diagnostics(
    instrument_results: Mapping[str, BacktestResult],
) -> tuple[float, Optional[float], Optional[dict[str, dict[str, float]]]]:
    fdms = [
        result.forecast_diversification_multiplier
        for result in instrument_results.values()
        if result.forecast_diversification_multiplier is not None
    ]
    average_fdm = float(sum(fdms) / len(fdms)) if fdms else 1.0

    frames = [
        pd.DataFrame.from_dict(result.forecast_correlations, orient="index")
        for result in instrument_results.values()
        if result.forecast_correlations
    ]
    if not frames:
        return average_fdm, None, None

    names = sorted({name for frame in frames for name in frame.index.union(frame.columns)})
    total = pd.DataFrame(0.0, index=names, columns=names)
    count = pd.DataFrame(0, index=names, columns=names)
    for frame in frames:
        aligned = frame.reindex(index=names, columns=names).astype("float64")
        total = total.add(aligned.fillna(0.0), fill_value=0.0)
        count = count.add(aligned.notna().astype(int), fill_value=0)

    average_correlation = total / count.replace(0, pd.NA)
    for name in names:
        average_correlation.loc[name, name] = 1.0
    return (
        average_fdm,
        calculate_average_correlation(average_correlation),
        correlation_to_dict(average_correlation),
    )
