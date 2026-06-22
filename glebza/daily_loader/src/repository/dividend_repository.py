"""Dividend event persistence."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

from repository.postgres_connection import connect


class DividendRepository:
    def upsert_dividends(self, instrument_id: int, rows: Sequence[Mapping]) -> int:
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
        conn = connect()
        affected = 0
        try:
            with conn.cursor() as cur:
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
                            row.get("created_at"),
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
