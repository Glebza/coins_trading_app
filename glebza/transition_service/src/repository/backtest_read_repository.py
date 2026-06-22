"""Read backtest runs and related Carver rows from the backtest database."""

from __future__ import annotations

from typing import Any, Optional

import psycopg2.extras

from repository.postgres_connection import connect
from transition_service.settings import Settings

RUN_STATUS_COMPLETED = "completed"


class BacktestReadRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_runs(
        self,
        *,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        conn = connect(
            database_url=self._settings.backtest_database_url,
            schema=self._settings.backtest_schema,
        )
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            params: list[Any] = []
            where = ""
            if status:
                where = "WHERE status = %s"
                params.append(status)
            limit_sql = ""
            if limit is not None:
                limit_sql = " LIMIT %s"
                params.append(limit)
            cur.execute(
                f"""
                SELECT id, strategy_id, portfolio_id, kline_interval, status,
                       COALESCE(annualized_return, cagr) AS annualized_return,
                       sharpe, started_at, finished_at, start_dt, end_dt
                FROM backtest_runs
                {where}
                ORDER BY started_at DESC NULLS LAST, id DESC
                {limit_sql}
                """,
                params,
            )
            rows = cur.fetchall()
            cur.close()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_run(self, run_id: int) -> Optional[dict[str, Any]]:
        conn = connect(
            database_url=self._settings.backtest_database_url,
            schema=self._settings.backtest_schema,
        )
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, strategy_id, portfolio_id, exchange_id, kline_interval, status,
                       COALESCE(annualized_return, cagr) AS annualized_return,
                       sharpe, started_at, finished_at, start_dt, end_dt,
                       forecast_diversification_multiplier,
                       forecast_average_correlation,
                       forecast_correlations
                FROM backtest_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_carver_strategy(self, strategy_id: int) -> Optional[dict[str, Any]]:
        conn = connect(
            database_url=self._settings.backtest_database_url,
            schema=self._settings.backtest_schema,
        )
        try:
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
            conn.close()

    def get_portfolio(self, portfolio_id: int) -> Optional[dict[str, Any]]:
        conn = connect(
            database_url=self._settings.backtest_database_url,
            schema=self._settings.backtest_schema,
        )
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, name, description FROM portfolio WHERE id = %s",
                (portfolio_id,),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_portfolio_instruments(self, portfolio_id: int) -> list[dict[str, Any]]:
        conn = connect(
            database_url=self._settings.backtest_database_url,
            schema=self._settings.backtest_schema,
        )
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT pi.instrument_id, pi.weight, pi.block_value, pi.lot_size,
                       i.ticker, i.instrument_type
                FROM portfolio_instruments pi
                JOIN instruments i ON i.id = pi.instrument_id
                WHERE pi.portfolio_id = %s
                ORDER BY i.ticker
                """,
                (portfolio_id,),
            )
            rows = cur.fetchall()
            cur.close()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_strategy_rules(self, strategy_id: int) -> list[dict[str, Any]]:
        conn = connect(
            database_url=self._settings.backtest_database_url,
            schema=self._settings.backtest_schema,
        )
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT sr.rule_group, sr.weight,
                       rv.name AS variation_name,
                       r.code AS rule_code
                FROM strategy_rules sr
                JOIN rule_variations rv ON rv.id = sr.rule_variation_id
                JOIN rules r ON r.id = rv.rule_id
                WHERE sr.strategy_id = %s
                ORDER BY r.code, rv.name
                """,
                (strategy_id,),
            )
            rows = cur.fetchall()
            cur.close()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_exchange(self, exchange_id: int) -> Optional[dict[str, Any]]:
        conn = connect(
            database_url=self._settings.backtest_database_url,
            schema=self._settings.backtest_schema,
        )
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, code, name, currency, tariff_name,
                       brokerage_rate_spot, brokerage_min_fee_spot,
                       brokerage_rate_futures, brokerage_rate_futures_alt,
                       brokerage_min_fee_futures,
                       exchange_fee_rate_spot, exchange_fee_rate_futures,
                       monthly_fee, effective_from, notes, max_capital_multiple
                FROM exchange
                WHERE id = %s
                """,
                (exchange_id,),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_instrument_share(self, instrument_id: int) -> Optional[dict[str, Any]]:
        conn = connect(
            database_url=self._settings.backtest_database_url,
            schema=self._settings.backtest_schema,
        )
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT instrument_id, figi, isin, ticker, class_code, lot, currency, name,
                       sector, buy_available_flag, sell_available_flag, short_enabled_flag,
                       api_trade_available_flag, for_qual_investor_flag, raw_payload
                FROM instrument_share
                WHERE instrument_id = %s
                """,
                (instrument_id,),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            conn.close()
