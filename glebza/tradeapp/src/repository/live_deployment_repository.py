"""Read-only DB access for live trading deployment (strategy, portfolio, frozen run)."""

from __future__ import annotations

import os
from typing import Any, List, Optional

import psycopg2
import psycopg2.extras

RUN_STATUS_COMPLETED = "completed"


class LiveDeploymentRepository:
    """
    Load live trading configuration from shared Carver tables.

    Uses the same schema as research (``backtests`` by default) but does not
    depend on backtest simulation or result persistence code.
    """

    def __init__(self, *, schema: Optional[str] = None) -> None:
        self._schema = schema or os.environ.get("DATABASE_DEFAULT_SCHEMA", "backtests")

    def _connection(self):
        connection = psycopg2.connect(os.environ["DATABASE_URL"])
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
                SELECT id, name, description,
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

    def list_strategy_rules(self, strategy_id: int) -> List[dict[str, Any]]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT sr.rule_group, sr.weight,
                       rv.id AS rule_variation_id,
                       rv.name AS variation_name,
                       rv.params,
                       r.code AS rule_code,
                       r.name AS rule_name
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
            if conn is not None:
                conn.close()

    def get_completed_run(self, run_id: int) -> Optional[dict[str, Any]]:
        """Load a completed research run snapshot used to freeze FDM for live trading."""
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, strategy_id, portfolio_id, kline_interval, status,
                       forecast_diversification_multiplier,
                       forecast_average_correlation,
                       forecast_correlations,
                       finished_at
                FROM backtest_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()

    def get_latest_completed_run(
        self,
        *,
        strategy_id: int,
        portfolio_id: int,
    ) -> Optional[dict[str, Any]]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, strategy_id, portfolio_id, kline_interval, status,
                       forecast_diversification_multiplier,
                       forecast_average_correlation,
                       forecast_correlations,
                       finished_at
                FROM backtest_runs
                WHERE strategy_id = %s
                  AND portfolio_id = %s
                  AND status = %s
                ORDER BY finished_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                (strategy_id, portfolio_id, RUN_STATUS_COMPLETED),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()
