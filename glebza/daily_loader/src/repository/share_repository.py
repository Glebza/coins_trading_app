"""Read and upsert MOEX shares in the database."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Callable, Optional

import psycopg2.extras
from psycopg2.extras import Json
from t_tech.invest.schemas import Share

from repository.postgres_connection import connect

logger = logging.getLogger(__name__)

_SHARE = "share"


def _share_raw_json(share: Share) -> Json:
    try:
        payload = json.loads(json.dumps(asdict(share), default=str))
        return Json(payload)
    except (TypeError, ValueError) as exc:
        logger.debug("raw_payload fallback: %s", exc)
        return Json({"repr": repr(share)})


class ShareRepository:
    def upsert_shares_batch(
        self,
        shares: list[Share],
        *,
        instruments_ticker_fn: Callable[[Share], str],
    ) -> dict[str, int]:
        if not shares:
            return {"fetched": 0, "inserted": 0, "updated": 0, "listed_in_db": self._count_shares()}

        conn = connect()
        inserted = 0
        updated = 0
        try:
            for share in shares:
                if self._share_exists(conn, share.isin.strip()):
                    updated += 1
                else:
                    inserted += 1
                self._upsert_share_cur(conn, share, instruments_ticker_fn(share))
            conn.commit()
            return {
                "fetched": len(shares),
                "inserted": inserted,
                "updated": updated,
                "listed_in_db": self._count_shares(conn),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _count_shares(self, conn=None) -> int:
        own_conn = conn is None
        if own_conn:
            conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM instruments i
                    JOIN instrument_share s ON s.instrument_id = i.id
                    WHERE i.instrument_type = %s
                    """,
                    (_SHARE,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
        finally:
            if own_conn:
                conn.close()

    def _share_exists(self, conn, isin: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM instrument_share WHERE isin = %s",
                (isin,),
            )
            return cur.fetchone() is not None

    def _upsert_share_cur(self, conn, share: Share, instruments_ticker: str) -> int:
        isin = share.isin.strip()
        if not isin:
            raise ValueError("Share.isin is required for upsert")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT instrument_id FROM instrument_share WHERE isin = %s",
                (isin,),
            )
            row = cur.fetchone()
            raw = _share_raw_json(share)
            short_enabled = bool(share.short_enabled_flag)

            if row:
                instrument_id = row[0]
                cur.execute(
                    """
                    UPDATE instruments SET ticker = %s
                    WHERE id = %s AND instrument_type = %s
                    """,
                    (instruments_ticker, instrument_id, _SHARE),
                )
                cur.execute(
                    """
                    UPDATE instrument_share SET
                        figi = %s,
                        isin = %s,
                        ticker = %s,
                        class_code = %s,
                        lot = %s,
                        currency = %s,
                        name = %s,
                        sector = %s,
                        buy_available_flag = %s,
                        sell_available_flag = %s,
                        short_enabled_flag = %s,
                        api_trade_available_flag = %s,
                        for_qual_investor_flag = %s,
                        raw_payload = %s
                    WHERE instrument_id = %s
                    """,
                    (
                        share.figi,
                        isin,
                        share.ticker,
                        share.class_code,
                        share.lot,
                        share.currency,
                        share.name,
                        share.sector,
                        share.buy_available_flag,
                        share.sell_available_flag,
                        short_enabled,
                        share.api_trade_available_flag,
                        share.for_qual_investor_flag,
                        raw,
                        instrument_id,
                    ),
                )
                return instrument_id

            cur.execute(
                """
                INSERT INTO instruments (ticker, instrument_type)
                VALUES (%s, %s)
                RETURNING id
                """,
                (instruments_ticker, _SHARE),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("INSERT INTO instruments did not return id")
            instrument_id = row[0]
            cur.execute(
                """
                INSERT INTO instrument_share (
                    instrument_id, figi, isin, ticker, class_code, lot, currency, name,
                    sector,
                    buy_available_flag, sell_available_flag, short_enabled_flag,
                    api_trade_available_flag, for_qual_investor_flag, raw_payload
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    instrument_id,
                    share.figi,
                    isin,
                    share.ticker,
                    share.class_code,
                    share.lot,
                    share.currency,
                    share.name,
                    share.sector,
                    share.buy_available_flag,
                    share.sell_available_flag,
                    short_enabled,
                    share.api_trade_available_flag,
                    share.for_qual_investor_flag,
                    raw,
                ),
            )
            return instrument_id

    def list_shares(self, *, limit: Optional[int] = None) -> list[dict]:
        sql = """
            SELECT i.id AS instrument_id,
                   i.ticker AS instruments_ticker,
                   s.figi,
                   s.class_code,
                   s.lot,
                   s.short_enabled_flag
            FROM instruments i
            JOIN instrument_share s ON s.instrument_id = i.id
            WHERE i.instrument_type = %s
            ORDER BY i.ticker
        """
        params: list = [_SHARE]
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)

        conn = connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()
