import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
import os


class BacktestRepository:

    def __get_connection(self):
        database_url = os.environ['DATABASE_URL']
        default_schema = os.environ['DATABASE_DEFAULT_SCHEMA']
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cur:
            cur.execute("SET search_path TO {}".format(default_schema))
            connection.commit()
        return connection

    def get_historical_klines(self, time_from, time_to, symbol, kline_interval):
        conn = self.__get_connection()
        cur = conn.cursor()
        cur.execute('''select id from instruments where ticker = %s''', (symbol,))
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
        cur.execute('''select id from instruments where ticker = %s''', (symbol,))
        ticker_id = cur.fetchone()
        sql_select = '''select max(id) from "order" where ticker_id = %s'''
        cur.execute(sql_select, (ticker_id,))
        return cur.fetchone()

    def get_deal_by_sell_order_id(self, order_id):
        conn = None
        deal = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                                      select id,buy_order_id,sell_order_id,start_date,end_date,ticker_id from deals
                                      where sell_order_id =%s
                                      ''', (order_id,))
            deal = cur.fetchone()
            cur.close()
            if deal is not None:
                deal = dict(deal)
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

        return deal

    def get_deals_between_close_orders_id(self, start_id,stop_id):
        conn = None
        deals = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                                              select id, buy_order_id,sell_order_id,start_date,end_date,ticker_id from deals
                                              where sell_order_id between %s and %s
                                              ''', (start_id,stop_id))
            deals = cur.fetchall()
            cur.close()
            if deals is not None:
                for deal in deals:
                    deal = dict(deal)
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

        return deals
