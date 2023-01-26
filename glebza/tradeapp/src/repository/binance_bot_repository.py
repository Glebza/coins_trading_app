import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
import os


class BinanceBotRepository:

    def __get_connection(self):

        database_url = os.environ['DATABASE_URL']
        print(database_url)
        connection = psycopg2.connect(database_url)
        return connection

    def save_order(self, order):
        con = self.__get_connection()
        cur = con.cursor()
        ticker_id = self.__get_ticker_id(con, order['symbol'])
        transact_time = datetime.fromtimestamp(order['time'] / 1000)
        print(transact_time)
        cur.execute('''
        insert into orders (id
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
        con.commit()
        con.close()

    def update_order_status(self, order_id, status, executedqty):
        print(order_id)
        print(status)
        print('executedqty = {}'.format(executedqty))
        con = self.__get_connection()
        cur = con.cursor()
        cur.execute('''
        update orders set status=%s , executedQty=%s
        where id =%s
        ''', (status, executedqty, order_id))
        con.commit()
        con.close()

    def save_deal(self, order):
        con = self.__get_connection()
        cur = con.cursor()
        symbol_id = self.__get_ticker_id(con, order['symbol'])
        transact_time = datetime.fromtimestamp(order['time'] / 1000)
        cur.execute('''insert into deals(buy_order_id,start_date,ticker_id) values (%s,%s,%s)'''
                    , (order['orderId'], transact_time, symbol_id))
        con.commit()
        con.close()

    def update_deal(self, buy_order, sell_order):
        con = self.__get_connection()
        cur = con.cursor()
        transact_time = datetime.fromtimestamp(sell_order['time'] / 1000)
        cur.execute('''
                update deals 
                set sell_order_id=%s, end_date =%s
                where buy_order_id =%s
                ''', (sell_order['orderId'], transact_time, buy_order['orderId']))
        con.commit()
        con.close()

    def get_orders_by_status(self, status):
        con = self.__get_connection()
        cur = con.cursor()
        cur.execute('''
                select * from orders
                where status =%s
                ''', (status,))
        orders = cur.fetchall()
        con.close()
        return orders

    def get_open_deal_order(self, symbol):
        order = None
        con = self.__get_connection()
        cur = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
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
                            ,clientorderid,transacttime,price,origqty,executedqty,status,type,side  from orders
                            where id =%s
                            ''', (deal['buy_order_id'],))
            order = cur.fetchone()
            if order:
                order = dict(order)
                order['orderId'] = order.pop('id')
                order['executedQty'] = order.pop('executedqty')

        con.close()
        return order

    def get_order_by_id(self, id):
        try:
            conn = self.__get_connection()
            cur = conn.cursor()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('''
                           select * from orders
                           where id =%s
                           ''', (id,))
            order = cur.fetchone()
            if order is not None:
                order = dict(order)
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

        return order

    def delete_order_by_id(self,id):
        rows_deleted = 0
        try:
            conn = self.__get_connection()
            cur = conn.cursor()
            cur.execute('''
                                   delete from orders
                                   where id =%s
                                   ''', (id,))
            rows_deleted = cur.rowcount
            conn.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(error)
        finally:
            if conn is not None:
                conn.close()

        return rows_deleted

    def __get_ticker_id(self, connection, symbol):
        cur = connection.cursor()
        cur.execute('select id from coins where ticker = %s', (symbol,))
        ticker_id = cur.fetchone()
        return ticker_id
