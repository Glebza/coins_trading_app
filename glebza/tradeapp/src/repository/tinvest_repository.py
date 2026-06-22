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

from datetime import datetime

from instrument_type import SHARE
from t_tech.invest.schemas import Share

logger = logging.getLogger(__name__)

_KLINE_INTERVALS = frozenset({"1m", "15m", "30m", "4h", "1d"})




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
        sector = share.sector
        short_enabled = bool(share.short_enabled_flag)

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
    
    def list_shares_by_tickers(self, ticker_list: List[str], limit: Optional[int] = None) -> List[dict]:

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
                WHERE i.instrument_type = %s AND i.ticker IN %s
                ORDER BY s.ticker NULLS LAST, s.figi
            """
            params: List[Any] = [SHARE, tuple(ticker_list)]
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

    def list_shares_filtered_by_liquidity_and_volatility(
        self,
        *,
        kline_interval: str = "1d",
        volatility_interval: str = "1d",
        volume_percentile: float = 0.60,
        min_annualized_volatility: float = 0.20,
        kline_start_dt: Optional[datetime] = None,
        exclude_for_qual_investor: bool = True,
    ) -> List[dict]:
        """
        Shares with median daily volume at or above the volume percentile and latest
        realized vol at or above ``min_annualized_volatility``.

        Uses ``kline_{interval}`` for median volume per ``ticker_id`` and the latest
        ``instrument_volatility`` row per instrument for ``volatility_interval``.
        """
        if kline_interval not in _KLINE_INTERVALS:
            raise ValueError(
                f"Unsupported kline_interval '{kline_interval}'. "
                f"Expected one of {sorted(_KLINE_INTERVALS)}"
            )
        if not 0 < volume_percentile <= 1:
            raise ValueError("volume_percentile must be in (0, 1]")
        if min_annualized_volatility <= 0:
            raise ValueError("min_annualized_volatility must be positive")

        kline_table = f"kline_{kline_interval}"
        kline_where = ""
        params: List[Any] = []
        if kline_start_dt is not None:
            kline_where = "WHERE k_interval >= %s"
            params.append(kline_start_dt)

        qual_clause = "AND s.for_qual_investor_flag IS NOT TRUE" if exclude_for_qual_investor else ""

        sql = f"""
            WITH per_ticker AS (
                SELECT
                    ticker_id,
                    percentile_disc(0.5) WITHIN GROUP (ORDER BY volume) AS med_volume
                FROM {kline_table}
                {kline_where}
                GROUP BY ticker_id
            ),
            med_vol_thresh AS (
                SELECT percentile_disc(%s) WITHIN GROUP (ORDER BY med_volume) AS p_threshold
                FROM per_ticker
            ),
            latest_vol AS (
                SELECT DISTINCT ON (instrument_id)
                    instrument_id,
                    annualized_volatility,
                    as_of AS vol_as_of,
                    interval_name
                FROM instrument_volatility
                WHERE interval_name = %s
                ORDER BY instrument_id, as_of DESC
            )
            SELECT
                i.id AS instrument_id,
                i.ticker AS instruments_ticker,
                s.name,
                s.for_qual_investor_flag,
                s.api_trade_available_flag,
                s.sector,
                s.short_enabled_flag,
                s.figi,
                s.class_code,
                s.lot,
                p.med_volume,
                lv.annualized_volatility,
                lv.vol_as_of,
                lv.interval_name
            FROM instruments i
            JOIN instrument_share s ON i.id = s.instrument_id
            JOIN per_ticker p ON i.id = p.ticker_id
            JOIN latest_vol lv ON i.id = lv.instrument_id
            CROSS JOIN med_vol_thresh mvt
            WHERE i.instrument_type = %s
              AND p.med_volume >= mvt.p_threshold
              AND lv.annualized_volatility >= %s
              {qual_clause}
            ORDER BY i.ticker
        """
        params.extend([volume_percentile, volatility_interval, SHARE, min_annualized_volatility])

        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            cur.close()
            return [dict(row) for row in rows]
        finally:
            if conn is not None:
                conn.close()

    def instrument_ids_with_min_kline_count(
        self,
        instrument_ids: List[int],
        interval: str,
        *,
        start_dt: datetime,
        end_dt: datetime,
        min_count: int,
    ) -> set[int]:
        """Return instrument ids with at least ``min_count`` klines in ``[start_dt, end_dt]``."""
        if not instrument_ids:
            return set()
        if interval not in _KLINE_INTERVALS:
            raise ValueError(
                f"Unsupported interval '{interval}'. Expected one of {sorted(_KLINE_INTERVALS)}"
            )
        if min_count < 1:
            raise ValueError("min_count must be at least 1")
        if end_dt <= start_dt:
            raise ValueError("end_dt must be after start_dt")

        kline_table = f"kline_{interval}"
        sql = f"""
            SELECT ticker_id
            FROM {kline_table}
            WHERE ticker_id = ANY(%s)
              AND k_interval >= %s
              AND k_interval <= %s
            GROUP BY ticker_id
            HAVING COUNT(*) >= %s
        """
        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor()
            cur.execute(sql, (instrument_ids, start_dt, end_dt, min_count))
            rows = cur.fetchall()
            cur.close()
            return {int(row[0]) for row in rows}
        finally:
            if conn is not None:
                conn.close()


