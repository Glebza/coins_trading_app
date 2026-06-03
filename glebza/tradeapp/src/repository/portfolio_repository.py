"""PostgreSQL access for Carver ``portfolio`` and ``portfolio_instruments`` tables."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional, Sequence

import psycopg2


class PortfolioRepository:
    """Persist portfolio definitions to ``public.portfolio`` (or configured schema)."""

    def __init__(self, *, schema: Optional[str] = None) -> None:
        self._schema = schema or os.environ.get("DATABASE_DEFAULT_SCHEMA", "public")

    def _connection(self):
        connection = psycopg2.connect(os.environ["DATABASE_URL"])
        with connection.cursor() as cur:
            cur.execute("SET search_path TO %s", (self._schema,))
        connection.commit()
        return connection

    def store_portfolio(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        instruments: Sequence[tuple[int, float, float, int]],
    ) -> int:
        """
        Insert ``portfolio`` and ``portfolio_instruments`` rows in one transaction.

        Each instrument tuple is ``(instrument_id, weight, block_value, lot_size)``.
        Returns the new ``portfolio.id``.
        """
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
