import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
import os
import  logging

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)
class BinanceBotRepository:

    def __init__(self):
        print('init repository class')


    def __get_connection(self):

        database_url = os.environ['DATABASE_URL']
        connection = psycopg2.connect(database_url)
        return connection

    def __get_ticker_id(self, connection, symbol):
        cur = connection.cursor()
        cur.execute('select id from coins where ticker = %s', (symbol,))
        ticker_id = cur.fetchone()
        return ticker_id

    def save_order(self, order):
        conn = self.__get_connection()
        cur = conn.cursor()
        ticker_id = self.__get_ticker_id(conn, order['symbol'])[0]
        transact_time = datetime.fromtimestamp(order['time'] / 1000)
        cur.execute('''
        insert into order (id
        ,ticker_id
        ,orderlistid
        ,clientorderid
        ,transacttime
        ,price
        ,origqty
        ,executedqty
        ,status
        ,type
        ,side)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', (order['orderId']
                                  , ticker_id
                                  , order['orderListId']
                                  , order['clientOrderId']
                                  , transact_time
                                  , order['price']
                                  , order['origQty']
                                  , order['executedQty']
                                  , order['status']
                                  , order['type']
                                  , order['side']
              ))
        conn.commit()
        cur.close()
        conn.close()

    def update_order_status(self, order_id, status, executedqty):
        print(order_id)
        print(status)
        print('executedqty = {}'.format(executedqty))
        conn = self.__get_connection()
        cur = conn.cursor()
        cur.execute('''
        update order set status=%s , executedQty=%s
        where id =%s
        ''', (status, executedqty, order_id))
        conn.commit()
        cur.close()
        conn.close()

    def get_order_by_id(self, id):
        conn = self.__get_connection()
        try:

            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                           select * from order
                           where id =%s
                           ''', (id,))
            order = cur.fetchone()
            cur.close()
            if order is not None:
                order = dict(order)
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

        return order

    def get_orders_by_status(self, status):
        conn = self.__get_connection()
        cur = conn.cursor()
        cur.execute('''
                   select * from order
                   where status =%s
                   ''', (status,))
        orders = cur.fetchall()
        cur.close()
        conn.close()
        return orders

    def delete_order_by_id(self, id):
        rows_deleted = 0
        conn = self.__get_connection()
        try:

            cur = conn.cursor()
            cur.execute('''
                                      delete from order
                                      where id =%s
                                      ''', (id,))
            rows_deleted = cur.rowcount
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

        return rows_deleted

    def save_deal(self, order):
        conn = self.__get_connection()
        try:

            cur = conn.cursor()
            symbol_id = self.__get_ticker_id(conn, order['symbol'])
            transact_time = datetime.fromtimestamp(order['time'] / 1000)
            cur.execute('''insert into deals(buy_order_id,start_date,ticker_id) values (%s,%s,%s)'''
                        , (order['orderId'], transact_time, symbol_id))
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

    def update_deal(self, buy_order, sell_order):
        conn = self.__get_connection()
        try:

            cur = conn.cursor()
            transact_time = datetime.fromtimestamp(sell_order['time'] / 1000)
            cur.execute('''
                    update deals 
                    set sell_order_id=%s, end_date =%s
                    where buy_order_id =%s
                    ''', (sell_order['orderId'], transact_time, buy_order['orderId']))
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

    def get_open_deal_order(self, symbol):
        order = None
        conn = self.__get_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                           select d.id,buy_order_id from deals d join coins c 
                           on d.ticker_id = c.id
                           where d.sell_order_id is null and c.ticker = %s
                           ''', (symbol,))
            deal = cur.fetchone()
            if deal is not None:
                deal = dict(deal)
                cur.execute('''
                                select id,ticker_id,orderlistid
                                ,clientorderid,transacttime,price,origqty,executedqty,status,type,side  from order
                                where id =%s
                                ''', (deal['buy_order_id'],))
                order = cur.fetchone()
                if order:
                    order = dict(order)
                    order['orderId'] = order.pop('id')
                    order['executedQty'] = order.pop('executedqty')
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()
        return order

    def get_deal_by_id(self, buy_order_id):
        conn = None
        try:
            conn = self.__get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                              select buy_order_id,sell_order_id,start_date,end_date,ticker_id from deals
                              where buy_order_id =%s
                              ''', (buy_order_id,))
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

    def delete_deal_by_id(self, buy_order_id):
        conn = None
        rows_deleted = 0
        try:
            conn = self.__get_connection()
            cur = conn.cursor()
            cur.execute('''
                                              delete from deals
                                              where deals.buy_order_id =%s
                                              ''', (buy_order_id,))
            rows_deleted = cur.rowcount
            conn.commit()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

        return rows_deleted








