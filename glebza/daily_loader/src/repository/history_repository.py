"""Klines and realized volatility persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import psycopg2.extras

from repository.postgres_connection import connect

_SUPPORTED_INTERVALS = frozenset({"1m", "15m", "30m", "4h", "1d"})


class HistoryRepository:
    def save_klines(self, instrument_id: int, klines: list[dict], interval: str) -> int:
        if interval not in _SUPPORTED_INTERVALS:
            raise ValueError(f"unsupported interval: {interval}")

        table_name = f"kline_{interval}"
        sql = f"""
            INSERT INTO {table_name} (
                ticker_id, k_interval, open_price, high_price, low_price, close_price, volume
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker_id, k_interval) DO NOTHING
        """
        conn = connect()
        inserted = 0
        try:
            with conn.cursor() as cur:
                for kline in klines:
                    interval_dt = kline["k_interval"]
                    if interval_dt.tzinfo is None:
                        interval_dt = interval_dt.replace(tzinfo=timezone.utc)
                    cur.execute(
                        sql,
                        (
                            instrument_id,
                            interval_dt,
                            Decimal(kline["open_price"]),
                            Decimal(kline["high_price"]),
                            Decimal(kline["low_price"]),
                            Decimal(kline["close_price"]),
                            int(kline["volume"]),
                        ),
                    )
                    inserted += cur.rowcount
            conn.commit()
            return inserted
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_klines(
        self,
        instrument_id: int,
        interval: str,
        *,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
    ) -> list[dict]:
        if interval not in _SUPPORTED_INTERVALS:
            raise ValueError(f"unsupported interval: {interval}")

        table_name = f"kline_{interval}"
        sql = f"""
            SELECT k_interval, close_price
            FROM {table_name}
            WHERE ticker_id = %s
        """
        params: list = [instrument_id]
        if start_dt is not None:
            sql += " AND k_interval >= %s"
            params.append(start_dt)
        if end_dt is not None:
            sql += " AND k_interval <= %s"
            params.append(end_dt)
        sql += " ORDER BY k_interval"

        conn = connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def save_volatility(
        self,
        instrument_id: int,
        interval: str,
        as_of: datetime,
        lookback_period: int,
        annualized_volatility: Decimal,
        observations: int,
    ) -> None:
        sql = """
            INSERT INTO instrument_volatility (
                instrument_id, interval_name, as_of, lookback_period,
                annualized_volatility, observations
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (instrument_id, interval_name, as_of) DO UPDATE
            SET lookback_period = EXCLUDED.lookback_period,
                annualized_volatility = EXCLUDED.annualized_volatility,
                observations = EXCLUDED.observations
        """
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        instrument_id,
                        interval,
                        as_of,
                        lookback_period,
                        annualized_volatility,
                        observations,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
