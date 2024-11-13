import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
import os


class BacktestRepository:

    def __get_connection(self):
        database_url = os.environ['DATABASE_URL']
        connection = psycopg2.connect(database_url)
        return connection

    def get_historical_klines(self, time_from, time_to, symbol, kline_interval):
        conn = self.__get_connection()
        cur = conn.cursor()
        cur.execute('''select id from coins where ticker = %s''', (symbol,))
        ticker_id = cur.fetchone()
        table_name = 'kline_{}'.format(kline_interval)
        sql_select = '''select k_interval , open_price,high_price,low_price,close_price,volume
         from  kline_{kline_interval} where ticker_id = %s  and k_interval between %s and %s order by k_interval
        '''.format(kline_interval=kline_interval)
        cur.execute(sql_select, (ticker_id, time_from, time_to,))
        return cur.fetchall()

    def save_klines_with_metricks(self, row):
        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor()
            conn.execute('''
            insert into k_line_training_data (k_interval,close_price, volume, market_cap, atr,
               rsi_15, rsi_9, macd,macd_sygnal, macd_diff, boll_low, boll_middle, boll_high)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ''', (row,))
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

    def get_last_order_id(self, symbol):
        conn = self.__get_connection()
        cur = conn.cursor()
        cur.execute('''select id from coins where ticker = %s''', (symbol,))
        ticker_id = cur.fetchone()
        sql_select = '''select max(id) from "order" where ticker_id = %s'''
        cur.execute(sql_select, (ticker_id,))
        return cur.fetchone()



