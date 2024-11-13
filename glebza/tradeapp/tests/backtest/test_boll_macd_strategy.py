import unittest
from unittest.mock import MagicMock

import numpy
from talib import MA_Type

import strategies.boll_macd_rsi as strategy
import glebza.tradeapp.src.service.order_service as service
import logging
import csv
from datetime import datetime, timedelta
from binance import Client
import os
from decimal import *

import talib

from glebza.tradeapp.tests.backtest.repository.backtest_repository import BacktestRepository
from glebza.tradeapp.src.repository.history_repository import HistoryRepository

CLOSE_PRICE_POSITION = 4

ACTION_BUY = 'BUY'

ACTION_WAIT = 'WAIT'

ACTION_SELL = 'SELL'

RSI_PERIOD = 15

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)

class StrategyBackTest(unittest.TestCase):

    def setUp(self):
        self.order_id = 1
        API_KEY = os.environ['API_KEY']
        API_SECRET = os.environ['API_SECRET']
        self.client = Client(API_KEY,API_SECRET)
        self.start_cash = 500
        self.symbol = 'BTCUSDT'
        warm_data = self.warm_up()
        self.close_prices = warm_data[0]
        self.volumes = warm_data[1]
        self.repository = BacktestRepository()
        self.history_repository = HistoryRepository()

    def test_boll_macd_rsi_strategy(self):
        buy_order = None
        start_date = datetime(2024, 1, 1, 0, 0, 0)
        end_date = datetime(2024, 1, 30, 23, 59, 59)
        klines = self.repository.get_historical_klines(start_date, end_date, self.symbol,
                                                       self.client.KLINE_INTERVAL_1MINUTE)
        buy_price, sell_price = 0, 0
        kline_number = 0
        for kline in klines:
            print("kline number {}".format(kline_number))
            closed_price = float(kline[CLOSE_PRICE_POSITION])
            start_interval = datetime.timestamp(kline[0]) * 1000
            self.close_prices.append(closed_price)
            track = strategy.process([self.close_prices], start_interval, buy_order)
            if track['action'] == ACTION_BUY:
                qty = round(self.start_cash / closed_price, 5)
                buy_order = self.prepare_mock_order(start_interval, qty, closed_price, 'BUY')
                service.open_deal(self.client, self.symbol, buy_price, qty)
            if track['action'] == ACTION_SELL:
                self.prepare_mock_order(start_interval, buy_order['executedQty'], closed_price, 'SELL')
                service.close_deal(self.client, self.symbol, closed_price, buy_order)
                buy_order = None

        self.assertEqual(True, False)


    def warm_up(self):
        logging.info(self.symbol)
        volumes = []
        closes = []
        end_date = datetime.now()
        start_date = (end_date - timedelta(days=1)).strftime("%d/%m/%Y, %H:%M:%S")
        klines = self.client.get_historical_klines(self.symbol, Client.KLINE_INTERVAL_1MINUTE, "01.03.2024 00:00:00",
                                                   '31.03.2024 23:59:59')

        start_interval = 0
        open_p = 1
        high = 2
        low = 3
        close = 4
        volume = 5
        for kline in klines:
            volumes.append(kline[volume])
            closes.append(float(kline[close]))
        print('historical data received')
        return closes, volumes

    def prepare_mock_order(self, time, qty, close_price, side):
        order = dict(
            {'symbol': 'BTCUSDT',
             'orderId': self.order_id,
             'orderListId': -1,
             'clientOrderId': 'bU2iE4DQGRsUP7euHmw5QE',
             'price': close_price,
             'origQty': qty,
             'executedQty': qty,
             'cummulativeQuoteQty': '530.00616000',
             'status': 'FILLED',
             'timeInForce': 'FOK',
             'type': 'LIMIT',
             'side': side,
             'stopPrice': '0.00000000', 'icebergQty': '0.00000000',
             'time': time,
             'updateTime': 1674685872599, 'isWorking': True, 'workingTime': 1674685872599,
             'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'NONE'})

        self.order_id = self.order_id + 1
        self.client.create_order = MagicMock(return_value=order)
        self.client.get_order = MagicMock(return_value=order)
        return order


if __name__ == '__main__':
    unittest.main()
