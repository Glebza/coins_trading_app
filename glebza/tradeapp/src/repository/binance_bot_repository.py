import psycopg2
from datetime import datetime
import os


class BinanceBotRepository:

    def __get_connection(self):
        DATABASE_URL = os.environ['DATABASE_URL']
        connection = psycopg2.connect(DATABASE_URL)
        return connection

    def save_order(self, order):
        con = self.__get_connection()
        cur = con.cursor()
        print(type(order['side']))
        cur.execute('select id from coins where ticker = %s', (order['symbol'],) )
        ticker_id = cur.fetchone()
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

