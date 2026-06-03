"""PostgreSQL access for instrument dividend events."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Mapping, Optional, Sequence

import psycopg2
import psycopg2.extras


class InstrumentDividendRepository:
    def __init__(self, *, schema: Optional[str] = None) -> None:
        self._schema = schema or os.environ.get("DATABASE_DEFAULT_SCHEMA", "public")

    def _connection(self):
        connection = psycopg2.connect(os.environ["DATABASE_URL"])
        with connection.cursor() as cur:
            cur.execute("SET search_path TO %s", (self._schema,))
        connection.commit()
        return connection

    def upsert_dividends(self, instrument_id: int, rows: Sequence[Mapping]) -> int:
        """Insert or update dividend events for one instrument."""
        if not rows:
            return 0

        sql = """
            INSERT INTO instrument_dividends (
                instrument_id, dividend_net, dividend_currency, payment_date,
                declared_date, last_buy_date, dividend_type, record_date,
                regularity, close_price, close_price_currency, yield_value,
                api_created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (instrument_id, record_date) DO UPDATE
            SET dividend_net = EXCLUDED.dividend_net,
                dividend_currency = EXCLUDED.dividend_currency,
                payment_date = EXCLUDED.payment_date,
                declared_date = EXCLUDED.declared_date,
                last_buy_date = EXCLUDED.last_buy_date,
                dividend_type = EXCLUDED.dividend_type,
                regularity = EXCLUDED.regularity,
                close_price = EXCLUDED.close_price,
                close_price_currency = EXCLUDED.close_price_currency,
                yield_value = EXCLUDED.yield_value,
                api_created_at = EXCLUDED.api_created_at
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
                        instrument_id,
                        Decimal(row["dividend_net"]),
                        row.get("dividend_currency"),
                        row.get("payment_date"),
                        row.get("declared_date"),
                        row.get("last_buy_date"),
                        row.get("dividend_type"),
                        row["record_date"],
                        row.get("regularity"),
                        Decimal(row["close_price"]) if row.get("close_price") is not None else None,
                        row.get("close_price_currency"),
                        Decimal(row["yield_value"]) if row.get("yield_value") is not None else None,
                        row.get("created_at") or row.get("api_created_at"),
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

    def list_dividends(
        self,
        instrument_id: int,
        *,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        known_as_of: Optional[datetime] = None,
    ) -> list[dict]:
        """Return dividend events ordered by record date.

        ``known_as_of`` filters out dividends that were not available at a forecast date.
        Uses ``api_created_at`` first, then ``declared_date`` as a fallback.
        """
        sql = """
            SELECT instrument_id, dividend_net, dividend_currency, payment_date,
                   declared_date, last_buy_date, dividend_type, record_date,
                   regularity, close_price, close_price_currency, yield_value,
                   api_created_at
            FROM instrument_dividends
            WHERE instrument_id = %s
        """
        params: list = [instrument_id]
        if start_dt is not None:
            sql += " AND record_date >= %s"
            params.append(start_dt)
        if end_dt is not None:
            sql += " AND record_date <= %s"
            params.append(end_dt)
        if known_as_of is not None:
            sql += " AND COALESCE(api_created_at, declared_date) <= %s"
            params.append(known_as_of)
        sql += " ORDER BY record_date"

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

    def dividends_series_for_dates(
        self,
        instrument_id: int,
        dates: Sequence[datetime],
        *,
        lookback_days: int = 365,
    ) -> list[dict]:
        """Align latest-known trailing dividend events to forecast dates."""
        rows: list[dict] = []
        for as_of in dates:
            start_dt = as_of - timedelta(days=lookback_days)
            dividends = self.list_dividends(
                instrument_id,
                start_dt=start_dt,
                end_dt=as_of,
                known_as_of=as_of,
            )
            rows.append({"as_of": as_of, "dividends": dividends})
        return rows
