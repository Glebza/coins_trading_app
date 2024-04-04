import psycopg2
import psycopg2.extras
from datetime import datetime
import os, logging

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)


class SignalBotRepository:

    def __init__(self):
        logger.debug('init  signal bot repository class')

    def __get_connection(self):
        database_url = os.environ['DATABASE_URL']
        connection = psycopg2.connect(database_url)
        return connection

    def get_signals_count_for_today(self, ):
        signals = None
        conn = None
        result = dict()
        try:
            conn = self.__get_connection()
            cur = self.__get_connection().cursor()
            cur.execute("""select symbol, count(*) as signal_count from signals s join coins c on s.id = c.id
                 where dt >= current_date group by s.id """)
            signals = cur.fetchall()
            if signals is not None:
                for signal in signals:
                    signal_dict = dict(signal)
                    result[signal_dict["symbol"]] = signal_dict
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()
        return result

    def save_signals_data(self, signals, interval) -> object:
        conn = None
        try:
            sql_insert = '''
             insert into signals (ticker_id, k_interval, open_price, high_price, low_price, close_price, volume)
             values (1,%s, %s, %s, %s, %s, %s);
             '''
            print(sql_insert)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
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
                # print(interval.strftime('%Y-%d-%m %H:%M:%S'))
                dbrows.append((interval, Decimal(kline[open_p]), Decimal(kline[high]),
                               Decimal(kline[low]), Decimal(kline[close]), kline[volume]))

                cur.executemany(sql_insert, dbrows)
                conn.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()
