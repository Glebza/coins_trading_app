"""Funding-rate persistence (RUONIA)."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

from repository.postgres_connection import connect


class FundingRateRepository:
    def upsert_rates(self, rows: Sequence[Mapping]) -> int:
        if not rows:
            return 0

        sql = """
            INSERT INTO funding_rates (
                rate_code, rate_date, annual_rate, source, status, published_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (rate_code, rate_date, source) DO UPDATE
            SET annual_rate = EXCLUDED.annual_rate,
                status = EXCLUDED.status,
                published_at = EXCLUDED.published_at
        """
        conn = connect()
        affected = 0
        try:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        sql,
                        (
                            row["rate_code"],
                            row["rate_date"],
                            Decimal(row["annual_rate"]),
                            row.get("source", "cbr"),
                            row.get("status"),
                            row.get("published_at"),
                        ),
                    )
                    affected += cur.rowcount
            conn.commit()
            return affected
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
