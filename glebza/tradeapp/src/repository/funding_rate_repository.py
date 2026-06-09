"""PostgreSQL access for funding-rate time series."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Optional, Sequence

import psycopg2
import psycopg2.extras


class FundingRateRepository:
    def __init__(self, *, schema: Optional[str] = None) -> None:
        self._schema = schema or os.environ.get("DATABASE_DEFAULT_SCHEMA", "public")

    def _connection(self):
        connection = psycopg2.connect(os.environ["DATABASE_URL"])
        with connection.cursor() as cur:
            cur.execute("SET search_path TO %s", (self._schema,))
        connection.commit()
        return connection

    def upsert_funding_rates(self, rows: Sequence[Mapping]) -> int:
        """Insert or update funding-rate rows. Returns affected row count."""
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
        conn = None
        affected = 0
        try:
            conn = self._connection()
            cur = conn.cursor()
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
            cur.close()
            return affected
        except Exception:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def list_funding_rates(
        self,
        *,
        rate_code: str = "RUONIA",
        source: str = "cbr",
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
    ) -> list[dict]:
        """Return funding rates ordered by rate date."""
        sql = """
            SELECT rate_code, rate_date, annual_rate, source, status, published_at
            FROM funding_rates
            WHERE rate_code = %s
              AND source = %s
        """
        params: list = [rate_code, source]
        if start_dt is not None:
            sql += " AND rate_date >= %s"
            params.append(start_dt.date())
        if end_dt is not None:
            sql += " AND rate_date <= %s"
            params.append(end_dt.date())
        sql += " ORDER BY rate_date"

        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            cur.close()
            return [dict(row) for row in rows]
        finally:
            if conn is not None:
                conn.close()

    def latest_funding_rate_as_of(
        self,
        as_of: datetime,
        *,
        rate_code: str = "RUONIA",
        source: str = "cbr",
    ) -> Optional[dict]:
        """Latest known funding rate as of a forecast timestamp.

        If ``published_at`` is missing, the rate is treated as known from the day after
        ``rate_date`` to avoid using same-day RUONIA before CBR publication.
        """
        sql = """
            SELECT rate_code, rate_date, annual_rate, source, status, published_at
            FROM funding_rates
            WHERE rate_code = %s
              AND source = %s
              AND COALESCE(published_at, rate_date + INTERVAL '1 day') <= %s
            ORDER BY rate_date DESC
            LIMIT 1
        """
        conn = None
        try:
            conn = self._connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, (rate_code, source, as_of))
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()

    def funding_rate_series_for_dates(
        self,
        dates: Sequence[datetime],
        *,
        rate_code: str = "RUONIA",
        source: str = "cbr",
    ) -> list[dict]:
        """Align latest-known funding rates to forecast dates."""
        return [
            {"as_of": as_of, "funding_rate": self.latest_funding_rate_as_of(as_of, rate_code=rate_code, source=source)}
            for as_of in dates
        ]
