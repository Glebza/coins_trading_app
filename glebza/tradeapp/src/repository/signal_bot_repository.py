from decimal import Decimal

import psycopg2
import psycopg2.extras
import os, logging

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s:%(asctime)s %(name) at line %(lineno)  %(message)s', level=logging.INFO)


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
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("""select ticker, count(*) as repeat_count from signals s join coins c on s.ticker_id = c.id
                 where dt >= current_date group by c.ticker """)
            signals = cur.fetchall()
            if signals is not None:
                for signal in signals:
                    signal_dict = dict(signal)
                    result[signal_dict["ticker"]] = signal_dict["repeat_count"]
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error,)
        finally:
            if conn is not None:
                conn.close()
        return result

    def __get_all_tickers(self, connection):
        cur = None
        result = dict()
        try:
            cur = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('select ticker,id from coins')
            tickers = cur.fetchall()
            if tickers is not None:
                for ticker in tickers:
                    ticker_dict = dict(ticker)
                    result[ticker_dict["ticker"]] = ticker_dict["id"]
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if cur is not None:
                cur.close()
        return result

    def save_signals_data(self, signals) -> object:
        conn = None
        result = []
        try:
            conn = self.__get_connection()
            cur = conn.cursor()
            sql_insert = '''
             insert into signals (dt,ticker_id, oi_percent_changed,cvd_percent_changed, price_change_24h )
             values (%s, %s, %s, %s, %s) RETURNING id;
             '''
            print(sql_insert)
            dbrows = []
            # date in mm-dd-yyyy format
            dt_idx = 0
            symbol_idx = 1
            oi_idx = 2
            cvd_idx = 3
            price_idx = 4
            tickers = self.__get_all_tickers(conn)
            for signal in signals:
                ticker_id = tickers[signal[symbol_idx]]
                if ticker_id is not None:
                    insert_data = (signal[dt_idx],ticker_id, signal[oi_idx], signal[cvd_idx],
                                   Decimal(signal[price_idx]))
                    cur.execute(sql_insert, insert_data)
                    result.append(cur.fetchone()[0])
            conn.commit()

        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()
        return result

    def delete_signals_by_(self, ids):
        conn = None
        separator = ', '
        ids_string = separator.join(str(e) for e in ids)

        try:
            conn = self.__get_connection()
            cur = conn.cursor()
            cur.execute('delete from signals where id in %s', (tuple(ids),))
            conn.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()
