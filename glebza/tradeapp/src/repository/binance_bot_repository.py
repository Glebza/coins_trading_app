import psycopg2
from datetime import datetime
import os


class BinanceBotRepository:

    def __get_connection(self):
        #DATABASE_URL = os.environ['DATABASE_URL']
        #connection = psycopg2.connect(dbname="postgres", user="glebza",password="glebzaDb1",hostaddr="45.141.76.98",port="5432")
        connection = psycopg2.connect(dbname="postgres", user="postgres",password="postgres",hostaddr="127.0.0.1",port="5433")
        return connection


    def save_order(self, order):
        con = self.__get_connection()
        cur = con.cursor()
        ticker_id = self.__get_ticker_id(con,order['symbol'])
        transact_time = datetime.fromtimestamp(order['transactTime']/1000)
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

    def update_order_status(self, order_id, status):
        print(order_id)
        print(status)
        con = self.__get_connection()
        cur = con.cursor()
        cur.execute('''
        update orders set status=%s 
        where id =%s
        ''', (status, order_id))
        con.commit()
        con.close()

    def save_deal(self, order):
        con = self.__get_connection()
        cur = con.cursor()
        symbol_id = self.__get_ticker_id(con,order['symbol'])
        transact_time = datetime.fromtimestamp(order['transactTime'] / 1000)
        cur.execute('''insert into deals(buy_order_id,start_date,ticker_id) values (%s,%s,%s)'''
                    ,(order['orderId'],transact_time,symbol_id ))
        con.commit()
        con.close()

    def update_deal(self,buy_order,sell_order):
        con = self.__get_connection()
        cur = con.cursor()
        transact_time = datetime.fromtimestamp(sell_order['transactTime'] / 1000)
        cur.execute('''
                update deals 
                set sell_order_id=%s, end_date =%s
                where buy_order_id =%s
                ''', (sell_order['orderId'],transact_time, buy_order['orderId']))
        con.commit()
        con.close()

    def get_orders_by_status(self, status):
        con = self.__get_connection()
        cur = con.cursor()
        cur.execute('''
                select * from orders
                where status =%s
                ''', (status, ))
        orders = cur.fetchall()
        con.close()
        return orders

    def get_open_deal_order(self,symbol):
        order = None
        con = self.__get_connection()
        cur = con.cursor()
        cur.execute('''
                       select * from deals d join coins c 
                       on d.ticker_id = c.id
                       where d.sell_order_id is null and c.ticker = %s
                       ''', (symbol,))
        deal = cur.fetchone()
        if deal is not None:
            cur.execute('''
                            select * from orders
                            where id =%s
                            ''', (deal.buy_order_id,))
            order = cur.fetchone()
        con.close()
        return order

    def __get_ticker_id(self, connection, symbol):
        cur = connection.cursor()
        cur.execute('select id from coins where ticker = %s', (symbol,))
        ticker_id = cur.fetchone()
        return ticker_id

