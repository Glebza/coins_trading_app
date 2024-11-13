import unittest
from unittest.mock import MagicMock
import argparse
import numpy
from talib import MA_Type

import strategies.deviations as strategy
import glebza.tradeapp.src.service.order_service as service
import logging
import csv
from datetime import datetime, timedelta
from binance import Client
import os
from decimal import *
from service.base_backtest_service import warm_up, prepare_mock_order
import talib

from glebza.tradeapp.tests.backtest.repository.backtest_repository import BacktestRepository

CLOSE_PRICE_POSITION = 4
HIGH_PRICE_POSITION = 2
LOW_PRICE_POSITION = 3
INTERVAL_POSITION = 0

ACTION_BUY = 'BUY'

ACTION_WAIT = 'WAIT'

ACTION_SELL = 'SELL'

RSI_PERIOD = 15

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)

parser = argparse.ArgumentParser(description="Run tests with custom arguments")
parser.add_argument('--kline_interval', type=str, help='1m or 1h ')
parser.add_argument('--backtest_start_date', type=str, help='dd.mm.yyyy hh24:Mi:ss')
parser.add_argument('--backtest_end_date', type=str, help='dd.mm.yyyy hh24:Mi:ss')
parser.add_argument('--start_cash', type=int, help='start money for trading')
parser.add_argument('--symbol', type=str, help='BTCUSDT or else')

args, unknown = parser.parse_known_args()
kline_interval = args.kline_interval
backtest_start_date = args.backtest_start_date
backtest_end_date = args.backtest_end_date
start_cash = args.start_cash
symbol = args.symbol


class DeviationsStrategyBackTest(unittest.TestCase):

    def setUp(self):
        API_KEY = os.environ['API_KEY']
        API_SECRET = os.environ['API_SECRET']
        self.client = Client(API_KEY, API_SECRET)
        self.repository = BacktestRepository()
        self.order_id = self.repository.get_last_order_id(symbol) + 1
        self.start_cash = start_cash
        self.kline_interval = kline_interval
        self.backtest_start_date = backtest_start_date
        self.backtest_end_date = backtest_end_date
        warm_data = warm_up(self.repository, self.kline_interval, self.backtest_start_date)
        self.close_prices = warm_data[0]
        self.volumes = warm_data[1]
        self.highs = warm_data[2]
        self.lows = warm_data[3]
        self.intervals = warm_data[4]

    def test_deviations_strategy(self):
        buy_order = None
        start_date = datetime.strptime(self.backtest_start_date, "%d.%m.%Y %H:%M:%S")
        end_date = datetime.strptime(self.backtest_end_date, "%d.%m.%Y %H:%M:%S")
        # start_date = datetime(2024, 10, 10, 19, 35, 0)
        # end_date = datetime(2024, 10, 11, 18, 35, 0)
        klines = self.repository.get_historical_klines(start_date, end_date, symbol,
                                                       self.kline_interval)
        buy_price, sell_price = 0, 0

        for kline in klines:
            closed_price = float(kline[CLOSE_PRICE_POSITION])
            high_price = float(kline[HIGH_PRICE_POSITION])
            low_price = float(kline[LOW_PRICE_POSITION])
            interval = kline[INTERVAL_POSITION]
            start_interval = datetime.timestamp(kline[0]) * 1000

            self.close_prices.append(closed_price)
            self.highs.append(high_price)
            self.lows.append(low_price)
            self.intervals.append(interval)
            # print("kline  {}".format(interval))
            track = strategy.process([self.close_prices, self.highs, self.lows], self.intervals, buy_order)
            if track['action'] == ACTION_BUY:
                qty = round(self.start_cash / closed_price, 5)
                buy_order = prepare_mock_order(order_id, start_interval, qty, closed_price, 'BUY')
                self.client.create_order = MagicMock(return_value=buy_order)
                self.client.get_order = MagicMock(return_value=buy_order)
                service.open_deal(self.client, self.symbol, buy_price, qty)
            if track['action'] == ACTION_SELL:
                sell_order = prepare_mock_order(order_id, start_interval, buy_order['executedQty'], closed_price,
                                                'SELL')
                self.client.create_order = MagicMock(return_value=sell_order)
                self.client.get_order = MagicMock(return_value=sell_order)
                service.close_deal(self.client, self.symbol, closed_price, buy_order)
                buy_order = None

        self.assertEqual(True, False)


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'] + unknown)
