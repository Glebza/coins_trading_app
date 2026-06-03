"""PostgreSQL access for Carver backtests (schema ``backtests`` on the backtest database)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from math import sqrt
from typing import Any, List, Optional

import psycopg2
import psycopg2.extras

from glebza.tradeapp.src.framework.account import TradingAccount
from glebza.tradeapp.src.framework.backtest.result import BacktestResult, PortfolioBacktestResult
logger = logging.getLogger(__name__)

RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(value: float | Decimal | int | None) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


@dataclass(frozen=True)
class BacktestRun:
    """Inputs for a new ``backtests.backtest_runs`` row (config snapshot)."""

    strategy_id: int
    portfolio_id: int
    exchange_id: int
    kline_interval: str
    start_dt: datetime
    end_dt: datetime
    initial_trading_capital: Decimal
    annualized_volatility_target: Decimal
    brokerage_rate_spot: Optional[Decimal] = None
    brokerage_rate_futures: Optional[Decimal] = None
    slippage_rate: Optional[Decimal] = None
    periods_per_year: Optional[int] = None
    backtest_mode: str = "in_sample"
    step_months: Optional[int] = None
    status: str = RUN_STATUS_RUNNING


class BacktestRepository:
    """
    Carver simulation persistence in ``backtests.*``.

    Connect via ``DATABASE_URL`` pointing at the **backtest** database and
    ``DATABASE_DEFAULT_SCHEMA=backtests`` (or pass ``schema=`` to the constructor).
    """

    def __init__(self, *, schema: Optional[str] = None) -> None:
        self._schema = schema or os.environ.get("DATABASE_DEFAULT_SCHEMA", "backtests")

    def _connection(self):
        database_url = os.environ["DATABASE_URL"]
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cur:
            cur.execute("SET search_path TO %s", (self._schema,))
        connection.commit()
        return connection

    def get_carver_strategy(self, strategy_id: int) -> Optional[dict[str, Any]]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, name, description, exchange_id,
                       initial_trading_capital, annualized_volatility_target,
                       max_capital_multiple, position_inertia,
                       trailing_stop_multiplier, slippage_rate
                FROM carver_strategy
                WHERE id = %s
                """,
                (strategy_id,),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()

    def get_portfolio_id_for_strategy(self, strategy_id: int) -> Optional[int]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT portfolio_id FROM strategy_portfolio WHERE strategy_id = %s",
                (strategy_id,),
            )
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row else None
        finally:
            if conn is not None:
                conn.close()

    def get_instrument_id_by_ticker(self, ticker: str) -> Optional[int]:
        key = ticker.strip()
        if not key:
            return None
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM instruments WHERE ticker = %s", (key,))
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row else None
        finally:
            if conn is not None:
                conn.close()

    def create_run(self, spec: BacktestRun) -> int:
        """Insert ``backtest_runs`` and return the new id."""
        conn = None
        started_at = _utc_now() if spec.status == RUN_STATUS_RUNNING else None
        try:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO backtest_runs (
                    strategy_id, portfolio_id, exchange_id,
                    kline_interval, start_dt, end_dt,
                    initial_trading_capital, annualized_volatility_target,
                    brokerage_rate_spot, brokerage_rate_futures, slippage_rate,
                    periods_per_year, backtest_mode, step_months, status, started_at
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING id
                """,
                (
                    spec.strategy_id,
                    spec.portfolio_id,
                    spec.exchange_id,
                    spec.kline_interval,
                    spec.start_dt,
                    spec.end_dt,
                    spec.initial_trading_capital,
                    spec.annualized_volatility_target,
                    spec.brokerage_rate_spot,
                    spec.brokerage_rate_futures,
                    spec.slippage_rate,
                    spec.periods_per_year,
                    spec.backtest_mode,
                    spec.step_months,
                    spec.status,
                    started_at,
                ),
            )
            run_id = int(cur.fetchone()[0])
            conn.commit()
            cur.close()
            return run_id
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()


    def get_first_carver_strategy_id(self) -> Optional[int]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM carver_strategy ORDER BY id LIMIT 1")
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row else None
        finally:
            if conn is not None:
                conn.close()

    def store_portfolio(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        instruments: list[tuple[int, float, float, int]],
    ) -> int:
        """Insert ``portfolio`` + ``portfolio_instruments`` in the backtests schema."""
        if not instruments:
            raise ValueError("portfolio must contain at least one instrument")

        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO portfolio (name, description)
                VALUES (%s, %s)
                RETURNING id
                """,
                (name, description),
            )
            portfolio_id = int(cur.fetchone()[0])
            for instrument_id, weight, block_value, lot_size in instruments:
                cur.execute(
                    """
                    INSERT INTO portfolio_instruments (
                        portfolio_id, instrument_id, weight, block_value, lot_size
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        portfolio_id,
                        instrument_id,
                        Decimal(str(weight)),
                        Decimal(str(block_value)),
                        lot_size,
                    ),
                )
            conn.commit()
            cur.close()
            return portfolio_id
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def store_run_start_for_portfolio_backtest(
        self,
        *,
        portfolio_id: int,
        exchange: dict[str, Any],
        strategy_id: int,
        kline_interval: str,
        start_dt: datetime,
        end_dt: datetime,
        account: TradingAccount,
        periods_per_year: Optional[int] = None,
        slippage_rate: Optional[Decimal] = None,
        backtest_mode: str = "in_sample",
        step_months: Optional[int] = None,
    ) -> int:
        """Snapshot account and exchange parameters on ``backtest_runs`` before the simulation starts."""
        exchange_id = int(exchange["id"])

        spec = BacktestRun(
            strategy_id=strategy_id,
            portfolio_id=portfolio_id,
            exchange_id=exchange_id,
            kline_interval=kline_interval,
            start_dt=start_dt,
            end_dt=end_dt,
            initial_trading_capital=account.trading_capital,
            annualized_volatility_target=Decimal(str(account.annualized_volatility_target)),
            brokerage_rate_spot=_to_decimal(exchange.get("brokerage_rate_spot")),
            brokerage_rate_futures=_to_decimal(exchange.get("brokerage_rate_futures")),
            slippage_rate=slippage_rate,
            periods_per_year=periods_per_year,
            backtest_mode=backtest_mode,
            step_months=step_months,
            status=RUN_STATUS_RUNNING,
        )
        return self.create_run(spec)

    def update_run_status(
        self,
        run_id: int,
        status: str,
        *,
        error_message: Optional[str] = None,
        mark_started: bool = False,
    ) -> None:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor()
            if mark_started:
                cur.execute(
                    """
                    UPDATE backtest_runs
                    SET status = %s, error_message = %s, started_at = COALESCE(started_at, %s)
                    WHERE id = %s
                    """,
                    (status, error_message, _utc_now(), run_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE backtest_runs
                    SET status = %s, error_message = %s
                    WHERE id = %s
                    """,
                    (status, error_message, run_id),
                )
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def save_run_result(self, run_id: int, result: BacktestResult) -> None:
        """Persist portfolio-level metrics on ``backtest_runs`` (single-instrument run)."""
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE backtest_runs
                SET status = %s,
                    finished_at = %s,
                    total_return = %s,
                    cagr = %s,
                    annualized_return = %s,
                    annualized_volatility = %s,
                    sharpe = %s,
                    max_drawdown = %s,
                    forecast_diversification_multiplier = %s,
                    forecast_average_correlation = %s,
                    forecast_correlations = %s,
                    error_message = NULL
                WHERE id = %s
                """,
                (
                    RUN_STATUS_COMPLETED,
                    _utc_now(),
                    _to_decimal(result.total_return),
                    _to_decimal(result.cagr),
                    _to_decimal(result.annualized_return),
                    _to_decimal(result.annualized_volatility),
                    _to_decimal(result.sharpe),
                    _to_decimal(result.max_drawdown),
                    _to_decimal(result.forecast_diversification_multiplier),
                    _to_decimal(result.forecast_average_correlation),
                    psycopg2.extras.Json(result.forecast_correlations) if result.forecast_correlations else None,
                    run_id,
                ),
            )
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def insert_run_instruments(
        self,
        run_id: int,
        instrument_results: dict[str, BacktestResult],
        *,
        ticker_to_instrument_id: Optional[dict[str, int]] = None,
    ) -> int:
        """
        Insert ``backtest_run_instruments`` rows for each sleeve.

        ``ticker_to_instrument_id`` avoids extra lookups when the caller already has ids.
        """
        if not instrument_results:
            return 0

        conn = None
        inserted = 0
        id_by_ticker = dict(ticker_to_instrument_id or {})
        try:
            conn = self._connection()
            cur = conn.cursor()
            for ticker, sleeve in instrument_results.items():
                instrument_id = id_by_ticker.get(ticker)
                if instrument_id is None:
                    cur.execute("SELECT id FROM instruments WHERE ticker = %s", (ticker.strip(),))
                    row = cur.fetchone()
                    if row is None:
                        logger.warning("Skipping backtest_run_instruments for unknown ticker=%s", ticker)
                        continue
                    instrument_id = int(row[0])
                    id_by_ticker[ticker] = instrument_id

                cur.execute(
                    """
                    INSERT INTO backtest_run_instruments (
                        backtest_run_id, instrument_id, ticker,
                        total_return, cagr, sharpe, max_drawdown,
                        forecast_diversification_multiplier,
                        forecast_average_correlation,
                        forecast_correlations
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        instrument_id,
                        ticker,
                        _to_decimal(sleeve.total_return),
                        _to_decimal(sleeve.cagr),
                        _to_decimal(sleeve.sharpe),
                        _to_decimal(sleeve.max_drawdown),
                        _to_decimal(sleeve.forecast_diversification_multiplier),
                        _to_decimal(sleeve.forecast_average_correlation),
                        psycopg2.extras.Json(sleeve.forecast_correlations) if sleeve.forecast_correlations else None,
                    ),
                )
                inserted += 1

            conn.commit()
            cur.close()
            return inserted
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def save_portfolio_run_result(
        self,
        run_id: int,
        result: PortfolioBacktestResult,
        *,
        ticker_to_instrument_id: Optional[dict[str, int]] = None,
    ) -> None:
        """Persist aggregated metrics and per-sleeve rows for a portfolio backtest."""
        self.save_run_result(run_id, _portfolio_result_as_backtest_result(result))
        self.insert_run_instruments(
            run_id,
            result.instrument_results,
            ticker_to_instrument_id=ticker_to_instrument_id,
        )
        self.insert_oos_stages(run_id, result)

    def insert_oos_stages(self, run_id: int, result: PortfolioBacktestResult) -> int:
        """Persist per-stage summaries for expanding OOS runs."""
        rows = result.rows
        if "oos_stage" not in rows.columns or rows["oos_stage"].dropna().empty:
            return 0

        conn = None
        inserted = 0
        try:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM backtest_run_oos_stages WHERE backtest_run_id = %s", (run_id,))
            for stage, stage_rows in rows.dropna(subset=["oos_stage"]).groupby("oos_stage", sort=True):
                metrics = _calculate_stage_metrics(stage_rows, result.periods_per_year)
                first = stage_rows.iloc[0]
                cur.execute(
                    """
                    INSERT INTO backtest_run_oos_stages (
                        backtest_run_id, stage_number,
                        train_start_dt, train_end_dt, test_start_dt, test_end_dt,
                        rows_count, total_return, cagr, annualized_return,
                        annualized_volatility, sharpe, max_drawdown,
                        forecast_diversification_multiplier,
                        forecast_average_correlation,
                        forecast_correlations
                    ) VALUES (
                        %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s
                    )
                    """,
                    (
                        run_id,
                        int(stage),
                        first["train_start_dt"],
                        first["train_end_dt"],
                        first["test_start_dt"],
                        first["test_end_dt"],
                        metrics["rows_count"],
                        _to_decimal(metrics["total_return"]),
                        _to_decimal(metrics["cagr"]),
                        _to_decimal(metrics["annualized_return"]),
                        _to_decimal(metrics["annualized_volatility"]),
                        _to_decimal(metrics["sharpe"]),
                        _to_decimal(metrics["max_drawdown"]),
                        _to_decimal(result.forecast_diversification_multiplier),
                        _to_decimal(result.forecast_average_correlation),
                        psycopg2.extras.Json(result.forecast_correlations) if result.forecast_correlations else None,
                    ),
                )
                inserted += 1
            conn.commit()
            cur.close()
            return inserted
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def fail_run(self, run_id: int, error_message: str) -> None:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE backtest_runs
                SET status = %s, error_message = %s, finished_at = %s
                WHERE id = %s
                """,
                (RUN_STATUS_FAILED, error_message, _utc_now(), run_id),
            )
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def get_run(self, run_id: int) -> Optional[dict[str, Any]]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM backtest_runs WHERE id = %s", (run_id,))
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()

    def list_run_instruments(self, run_id: int) -> List[dict[str, Any]]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, backtest_run_id, instrument_id, ticker,
                       total_return, sharpe, max_drawdown
                FROM backtest_run_instruments
                WHERE backtest_run_id = %s
                ORDER BY ticker
                """,
                (run_id,),
            )
            rows = cur.fetchall()
            cur.close()
            return [dict(r) for r in rows]
        finally:
            if conn is not None:
                conn.close()

    def list_runs(self, *, limit: int = 50) -> List[dict[str, Any]]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, strategy_id, portfolio_id, exchange_id,
                       kline_interval, start_dt, end_dt, status,
                       total_return, sharpe, max_drawdown,
                       started_at, finished_at
                FROM backtest_runs
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            cur.close()
            return [dict(r) for r in rows]
        finally:
            if conn is not None:
                conn.close()


def _portfolio_result_as_backtest_result(result: PortfolioBacktestResult) -> BacktestResult:
    """Map portfolio aggregates to the shape stored on ``backtest_runs``."""
    return BacktestResult(
        rows=result.rows,
        total_return=result.total_return,
        cagr=result.cagr,
        annualized_return=result.annualized_return,
        annualized_volatility=result.annualized_volatility,
        sharpe=result.sharpe,
        max_drawdown=result.max_drawdown,
        forecast_diversification_multiplier=result.forecast_diversification_multiplier,
        forecast_average_correlation=result.forecast_average_correlation,
        forecast_correlations=result.forecast_correlations,
        periods_per_year=result.periods_per_year,
    )


def _calculate_stage_metrics(stage_rows, periods_per_year: int) -> dict[str, float | int]:
    returns = stage_rows["portfolio_return"]
    equity = (1.0 + returns).cumprod()
    drawdown = (equity / equity.cummax()) - 1.0
    total_return = float(equity.iloc[-1] - 1.0)
    return_volatility = float(returns.std(ddof=1))
    if return_volatility != return_volatility:
        return_volatility = 0.0
    annualized_return = float(returns.mean()) * periods_per_year
    annualized_volatility = return_volatility * sqrt(periods_per_year)
    sharpe = annualized_return / annualized_volatility if annualized_volatility else 0.0
    return {
        "rows_count": int(len(stage_rows)),
        "total_return": total_return,
        "cagr": _calculate_stage_cagr(stage_rows, total_return),
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
    }


def _calculate_stage_cagr(stage_rows, total_return: float) -> float:
    if len(stage_rows.index) < 2:
        return total_return
    dates = stage_rows.index
    elapsed_days = (dates[-1] - dates[0]).total_seconds() / 86_400
    years = elapsed_days / 365.25
    if years <= 0:
        return total_return
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)
