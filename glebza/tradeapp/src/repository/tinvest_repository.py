"""CRUD for T‑Invest shares: ``instruments`` + ``instrument_share`` (``instrument_type = share``)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from typing import Any, List, Optional

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json

from instrument_type import SHARE
from t_tech.invest.schemas import Share

from framework.instruments.instrument import share_sector

logger = logging.getLogger(__name__)




def _share_raw_json(share: Share) -> Any:
    """Serialize ``Share`` for ``raw_payload`` JSONB (best-effort)."""
    try:
        payload = json.loads(json.dumps(asdict(share), default=str))
        return Json(payload)
    except (TypeError, ValueError) as e:
        logger.debug("raw_payload fallback: %s", e)
        return Json({"repr": repr(share)})


class TinvestRepository:
    def __get_connection(self):
        database_url = os.environ["DATABASE_URL"]
        default_schema = os.environ.get("DATABASE_DEFAULT_SCHEMA", "public")
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cur:
            cur.execute("SET search_path TO %s", (default_schema,))
        connection.commit()
        return connection

    def upsert_share(self, share: Share, *, instruments_ticker: str) -> int:
        """Insert or update one share by ``isin`` (lookup key). Returns ``instruments.id``."""
        conn = None
        try:
            conn = self.__get_connection()
            iid = self._upsert_share_cur(conn, share, instruments_ticker)
            conn.commit()
            return iid
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def upsert_shares_batch(self, shares: List[Share], *, instruments_ticker_fn) -> int:
        """
        Persist many shares in one transaction.
        Each row is matched by ``isin`` (non-empty); ``instruments_ticker_fn(share) -> str`` sets ``instruments.ticker``.
        """
        if not shares:
            return 0
        conn = None
        try:
            conn = self.__get_connection()
            for share in shares:
                self._upsert_share_cur(conn, share, instruments_ticker_fn(share))
            conn.commit()
            return len(shares)
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def _upsert_share_cur(self, conn, share: Share, instruments_ticker: str) -> int:
        cur = conn.cursor()
        figi = share.figi
        isin = share.isin.strip()
        if not isin:
            raise ValueError("Share.isin is required for upsert (identity key)")

        cur.execute(
            "SELECT instrument_id FROM instrument_share WHERE isin = %s",
            (isin,),
        )
        row = cur.fetchone()
        raw = _share_raw_json(share)

        t_ticker = instruments_ticker
        t_share = share.ticker
        class_code = share.class_code
        lot = share.lot
        currency = share.currency
        name = share.name
        sector = share_sector(share)
        short_enabled = bool(getattr(share, "short_enabled_flag", False))

        if row:
            instrument_id = row[0]
            cur.execute(
                """
                UPDATE instruments SET ticker = %s
                WHERE id = %s AND instrument_type = %s
                """,
                (t_ticker, instrument_id, SHARE),
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
                    figi,
                    isin,
                    t_share,
                    class_code,
                    lot,
                    currency,
                    name,
                    sector,
                    share.buy_available_flag,
                    share.sell_available_flag,
                    short_enabled,
                    share.api_trade_available_flag,
                    share.for_qual_investor_flag,
                    raw,
                    instrument_id,
                ),
            )
            cur.close()
            return instrument_id

        cur.execute(
            """
            INSERT INTO instruments (ticker, instrument_type)
            VALUES (%s, %s)
            RETURNING id
            """,
            (t_ticker, SHARE),
        )
        instrument_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO instrument_share (
                instrument_id, figi, isin, ticker, class_code, lot, currency, name,
                sector,
                buy_available_flag, sell_available_flag, short_enabled_flag, api_trade_available_flag,
                for_qual_investor_flag, raw_payload
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                instrument_id,
                figi,
                isin,
                t_share,
                class_code,
                lot,
                currency,
                name,
                sector,
                share.buy_available_flag,
                share.sell_available_flag,
                short_enabled,
                share.api_trade_available_flag,
                share.for_qual_investor_flag,
                raw,
            ),
        )
        cur.close()
        return instrument_id

    def get_by_isin(self, isin: str) -> Optional[dict]:
        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                """
                SELECT i.id AS instrument_id, i.ticker AS instruments_ticker, i.instrument_type,
                       s.figi, s.isin, s.ticker AS listing_ticker, s.class_code, s.lot,
                       s.currency, s.name, s.sector,
                       s.buy_available_flag, s.sell_available_flag,
                       s.short_enabled_flag,
                       s.api_trade_available_flag, s.for_qual_investor_flag, s.raw_payload
                FROM instruments i
                JOIN instrument_share s ON s.instrument_id = i.id
                WHERE s.isin = %s AND i.instrument_type = %s
                """,
                (isin, SHARE),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()

    def get_by_ticker(self, ticker: str) -> Optional[dict]:
        """
        Resolve by ``instruments.ticker`` (listing ticker, same as ``instruments_ticker`` in list/get rows).
        """
        key = ticker.strip()
        if not key:
            return None
        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                """
                SELECT i.id AS instrument_id, i.ticker AS instruments_ticker, i.instrument_type,
                       s.figi, s.isin, s.ticker AS listing_ticker, s.class_code, s.lot,
                       s.currency, s.name, s.sector,
                       s.buy_available_flag, s.sell_available_flag,
                       s.short_enabled_flag,
                       s.api_trade_available_flag, s.for_qual_investor_flag, s.raw_payload
                FROM instruments i
                JOIN instrument_share s ON s.instrument_id = i.id
                WHERE i.ticker = %s AND i.instrument_type = %s
                """,
                (key, SHARE),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()

    def get_by_instrument_id(self, instrument_id: int) -> Optional[dict]:
        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                """
                SELECT i.id AS instrument_id, i.ticker AS instruments_ticker, i.instrument_type,
                       s.figi, s.isin, s.ticker AS listing_ticker, s.class_code, s.lot,
                       s.currency, s.name, s.sector,
                       s.buy_available_flag, s.sell_available_flag,
                       s.short_enabled_flag,
                       s.api_trade_available_flag, s.for_qual_investor_flag, s.raw_payload
                FROM instruments i
                JOIN instrument_share s ON s.instrument_id = i.id
                WHERE i.id = %s AND i.instrument_type = %s
                """,
                (instrument_id, SHARE),
            )
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        finally:
            if conn is not None:
                conn.close()

    def list_shares(self, limit: Optional[int] = None) -> List[dict]:
        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            sql = """
                SELECT i.id AS instrument_id, i.ticker AS instruments_ticker, i.instrument_type,
                       s.figi, s.isin, s.ticker AS listing_ticker, s.class_code, s.lot,
                       s.currency, s.name, s.sector,
                       s.buy_available_flag, s.sell_available_flag,
                       s.short_enabled_flag,
                       s.api_trade_available_flag, s.for_qual_investor_flag, s.raw_payload
                FROM instruments i
                JOIN instrument_share s ON s.instrument_id = i.id
                WHERE i.instrument_type = %s
                ORDER BY s.ticker NULLS LAST, s.figi
            """
            params: List[Any] = [SHARE]
            if limit is not None:
                sql += " LIMIT %s"
                params.append(limit)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            cur.close()
            return [dict(r) for r in rows]
        finally:
            if conn is not None:
                conn.close()

    def delete_by_isin(self, isin: str) -> bool:
        """Delete the ``instruments`` row (child ``instrument_share`` removed via FK ON DELETE CASCADE)."""
        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                DELETE FROM instruments
                WHERE id = (
                    SELECT s.instrument_id FROM instrument_share s
                    INNER JOIN instruments i ON i.id = s.instrument_id
                    WHERE s.isin = %s AND i.instrument_type = %s
                )
                """,
                (isin, SHARE),
            )
            deleted = cur.rowcount > 0
            conn.commit()
            cur.close()
            return deleted
        except (Exception, psycopg2.DatabaseError):
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()
