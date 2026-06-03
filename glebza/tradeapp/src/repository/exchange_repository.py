"""PostgreSQL access for ``exchange`` rows."""

from __future__ import annotations

import os
from typing import Any, Optional

import psycopg2
import psycopg2.extras


class ExchangeRepository:
    """Load exchange definitions from the configured schema."""

    def __init__(self, *, schema: Optional[str] = None) -> None:
        self._schema = schema or os.environ.get("DATABASE_DEFAULT_SCHEMA", "public")

    def _connection(self):
        connection = psycopg2.connect(os.environ["DATABASE_URL"])
        with connection.cursor() as cur:
            cur.execute("SET search_path TO %s", (self._schema,))
        connection.commit()
        return connection

    def get_exchange_by_code(self, code: str) -> Optional[dict[str, Any]]:
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT id, code, name, currency, tariff_name,
                       brokerage_rate_spot, brokerage_rate_futures,
                       brokerage_min_fee_spot, monthly_fee, effective_from,
                       max_capital_multiple
                FROM exchange
                WHERE code = %s
                """,
                (code.strip(),),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()

