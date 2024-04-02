import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
import os
from decimal import *


class HistoryRepository:

    def __init__(self):
        print('init history repository class')

    def __get_connection(self):
        database_url = os.environ['DATABASE_URL']
        connection = psycopg2.connect(database_url)
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

                interval = datetime.fromtimestamp(kline[start_interval] / 1000)
                #print(interval.strftime('%Y-%d-%m %H:%M:%S'))
                dbrows.append((interval, Decimal(kline[open_p]), Decimal(kline[high]),
                               Decimal(kline[low]), Decimal(kline[close]), kline[volume]))

                cur.executemany(sql_insert, dbrows)
                conn.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()
