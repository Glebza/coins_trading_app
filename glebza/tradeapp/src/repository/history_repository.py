import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
import os
from decimal import *
from typing import Optional
import pytz


class HistoryRepository:
    _SUPPORTED_INTERVALS = {"1m", "15m", "30m", "4h", "1d"}

    def __init__(self):
        print('init history repository class')

    def __get_connection(self):
        database_url = os.environ['DATABASE_URL']
        default_schema = os.environ['DATABASE_DEFAULT_SCHEMA']
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cur:
            cur.execute("SET search_path TO {}".format(default_schema))
            connection.commit()
        return connection

    def save_klines_data(self, klines, interval) -> object:
        conn = None
        try:
            table_name = "kline_{s}".format(s=interval)
            sql_insert = '''
            insert into {table_name} (ticker_id, k_interval, open_price, high_price, low_price, close_price, volume)
            values (1,%s, %s, %s, %s, %s, %s);
            '''.format(table_name=table_name)
            print(sql_insert)
            conn = self.__get_connection()
            cur = conn.cursor()
            dbrows = []
            # date in mm-dd-yyyy format
            start_interval = 0
            open_p = 1
            high = 2
            low = 3
            close = 4
            volume = 5
            for kline in klines:
                timezone = pytz.timezone('UTC')
                print(kline[start_interval])
                interval = datetime.fromtimestamp(kline[start_interval]/1000, tz=timezone)
                print(interval)
                #print(interval.strftime('%Y-%d-%m %H:%M:%S'))
                cur.execute(sql_insert, (interval, Decimal(kline[open_p]), Decimal(kline[high]),
                               Decimal(kline[low]), Decimal(kline[close]), kline[volume]))
            conn.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

    def save_tinvest_klines_data(self, instrument_id: int, klines: list[dict], interval: str) -> int:
        conn = None
        inserted = 0
        if interval not in self._SUPPORTED_INTERVALS:
            raise ValueError(f"Unsupported interval '{interval}'. Expected one of {sorted(self._SUPPORTED_INTERVALS)}")

        try:
            table_name = f"kline_{interval}"
            sql_insert = f'''
            INSERT INTO {table_name} (ticker_id, k_interval, open_price, high_price, low_price, close_price, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker_id, k_interval) DO NOTHING;
            '''

            conn = self.__get_connection()
            cur = conn.cursor()
            for kline in klines:
                interval_dt = kline["k_interval"]
                if interval_dt.tzinfo is None:
                    interval_dt = interval_dt.replace(tzinfo=pytz.UTC)

                cur.execute(
                    sql_insert,
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
            cur.close()
            return inserted
        except (Exception, psycopg2.DatabaseError) as error:
            if conn is not None:
                conn.rollback()
            logging.error(error)
            raise
        finally:
            if conn is not None:
                conn.close()

    def get_klines_by_instrument(self, instrument_id: int, interval: str,
                                 start_dt: Optional[datetime] = None,
                                 end_dt: Optional[datetime] = None,
                                 limit: Optional[int] = None) -> list[dict]:
        conn = None
        if interval not in self._SUPPORTED_INTERVALS:
            raise ValueError(f"Unsupported interval '{interval}'. Expected one of {sorted(self._SUPPORTED_INTERVALS)}")

        try:
            table_name = f"kline_{interval}"
            sql = f"""
            SELECT ticker_id, k_interval, open_price, high_price, low_price, close_price, volume
            FROM {table_name}
            WHERE ticker_id = %s
            """
            params = [instrument_id]
            if start_dt is not None:
                sql += " AND k_interval >= %s"
                params.append(start_dt)
            if end_dt is not None:
                sql += " AND k_interval <= %s"
                params.append(end_dt)
            sql += " ORDER BY k_interval"
            if limit is not None:
                sql += " LIMIT %s"
                params.append(limit)

            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            cur.close()
            return [dict(r) for r in rows]
        finally:
            if conn is not None:
                conn.close()

    def save_instrument_volatility(self, instrument_id: int, interval: str, as_of: datetime,
                                   lookback_period: int, annualized_volatility: Decimal,
                                   observations: int) -> int:
        conn = None
        try:
            sql = """
            INSERT INTO instrument_volatility (
                instrument_id, interval_name, as_of, lookback_period, annualized_volatility, observations
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (instrument_id, interval_name, as_of) DO UPDATE
            SET lookback_period = EXCLUDED.lookback_period,
                annualized_volatility = EXCLUDED.annualized_volatility,
                observations = EXCLUDED.observations;
            """
            conn = self.__get_connection()
            cur = conn.cursor()
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
            cur.close()
            return 1
        except (Exception, psycopg2.DatabaseError) as error:
            if conn is not None:
                conn.rollback()
            logging.error(error)
            raise
        finally:
            if conn is not None:
                conn.close()
