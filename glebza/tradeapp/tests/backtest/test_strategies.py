from unittest.mock import MagicMock
import argparse
from glebza.tradeapp.src.strategies.deviations import DeviationsStrategy
import glebza.tradeapp.src.strategies.boll_macd_rsi as boll_macd_rsi
import glebza.tradeapp.src.service.order_service as service
import logging
from datetime import datetime, timedelta, timezone
from binance import Client
import os
from glebza.tradeapp.tests.backtest.repository.backtest_launch_repository import BacktestLaunchRepository
from glebza.tradeapp.tests.backtest.repository.backtest_result_repository import BacktestResultRepository
from glebza.tradeapp.tests.backtest.service.base_backtest_service import prepare_mock_order
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
parser.add_argument('--backtest_interval', type=str, help='month or day or year')
parser.add_argument('--start_cash', type=int, help='start money for trading')
parser.add_argument('--symbol', type=str, help='BTCUSDT or else')
parser.add_argument('--strategy_name', type=str, help='trading strategy')

args, unknown = parser.parse_known_args()
kline_interval = args.kline_interval
backtest_start_date = args.backtest_start_date
backtest_end_date = args.backtest_end_date
start_cash = args.start_cash
symbol = args.symbol
backtest_interval = args.backtest_interval
strategy_name = args.strategy_name


class StrategyBackTest():
    def setUp(self):
        API_KEY = os.environ['API_KEY']
        API_SECRET = os.environ['API_SECRET']
        self.client = Client(API_KEY, API_SECRET)
        self.repository = BacktestRepository()
        self.backtest_launch_repo = BacktestLaunchRepository()
        self.backtest_result_repo = BacktestResultRepository()
        last_order = self.repository.get_last_order_id(symbol)[0]
        self.order_id = 1
        if last_order:
            self.order_id += last_order
        self.start_cash = start_cash
        self.kline_interval = kline_interval
        self.backtest_start_date = backtest_start_date
        self.backtest_end_date = backtest_end_date

    def test_strategy(self):
        new_launch = self.backtest_launch_repo.add_backtest_launch(
            launch_dtm=datetime.now(),
            backtest_start=backtest_start_date,
            backtest_end=backtest_end_date,
            backtest_interval=backtest_interval,
            kline_interval=kline_interval,
            strategy_details_id=1,
            slippage=0,
            commission=0,
            start_money=1000,
            risk_factor=0
        )

        print(f"Backtest Launch created with ID: {new_launch.id}")
        backtest_start_dtm_gmt3 = datetime.strptime(self.backtest_start_date,
                                                    "%m.%d.%Y %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=3)))

        backtest_end_dtm_gmt3 = datetime.strptime(self.backtest_end_date,
                                                  "%m.%d.%Y %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=3)))
        backtest_start_dtm = backtest_start_dtm_gmt3.astimezone(timezone.utc)
        backtest_end_dtm = backtest_end_dtm_gmt3.astimezone(timezone.utc)
        # start_date = datetime(2024, 10, 10, 19, 35, 0)
        # end_date = datetime(2024, 10, 11, 18, 35, 0)
        start_date = backtest_start_dtm
        if backtest_interval == "day":
            print("Daily iterations")
            print(f"Backtest start start dtm : {start_date} and Backtest end dtm {backtest_end_dtm}")
            while start_date < backtest_end_dtm:

                buy_order = None
                end_date = start_date + timedelta(days=1)
                self.close_prices = []
                self.volumes = []
                self.highs = []
                self.lows = []
                self.intervals = []
                klines = self.repository.get_historical_klines(start_date, end_date, symbol, self.kline_interval)
                buy_price, sell_price = 0, 0
                close_orders = []
                warm_up_iterations = 50
                if strategy_name == "deviations":
                    config = {
                        'peak_range_in_candles': 4,
                        'look_back_period': 20,
                        'retest_price_error_rate': 10,
                        'lowest_price_error_range': 3,
                        'point3_price_error_rate': 3,
                        'min_range_from_base_to_peak': 100,
                    }
                    strategy = DeviationsStrategy(config)
                else:
                    strategy = boll_macd_rsi
                for kline in klines:

                    closed_price = float(kline[CLOSE_PRICE_POSITION])
                    high_price = float(kline[HIGH_PRICE_POSITION])
                    low_price = float(kline[LOW_PRICE_POSITION])
                    interval = kline[INTERVAL_POSITION]
                    start_interval = datetime.timestamp(kline[INTERVAL_POSITION]) * 1000
                    self.close_prices.append(closed_price)
                    self.highs.append(high_price)
                    self.lows.append(low_price)
                    self.intervals.append(interval)
                    if warm_up_iterations > 0:
                        warm_up_iterations -= 1
                        continue

                    track = strategy.process([self.close_prices, self.highs, self.lows], self.intervals, buy_order)
                    if track['action'] == ACTION_BUY:
                        qty = round(self.start_cash / closed_price, 5)
                        buy_order = self.make_mock_order(closed_price, qty, start_interval, 'BUY')
                        service.open_deal(self.client, symbol, buy_price, qty)
                    if track['action'] == ACTION_SELL:
                        self.make_mock_order(closed_price, buy_order['executedQty'], start_interval, 'SELL')
                        close_orders.append(service.close_deal(self.client, symbol, closed_price, buy_order))
                        buy_order = None

                if buy_order:
                    self.make_mock_order(self.close_prices[-1], buy_order['executedQty'],
                                         datetime.timestamp(self.intervals[-1]) * 1000, 'SELL')
                    close_orders.append(
                        service.close_deal(self.client, symbol, self.close_prices[-1], buy_order))
                    buy_order = None

                self.evaluate_profit(close_orders, end_date, new_launch, start_date)
                self.backtest_launch_repo.close_session()
                self.backtest_result_repo.close_session()
                start_date = end_date
                klines = []

        if kline_interval == "month":
            end_date = (start_date + timedelta(days=1)).strftime("%d.%m.%Y %H:%M:%S")

    def evaluate_profit(self, close_orders, end_date, new_launch, start_date):
        if len(close_orders) > 0:
            if len(close_orders) > 1:
                deals = self.repository.get_deals_between_close_orders_id(close_orders[0]['orderId'],
                                                                          close_orders[-1]['orderId'])
                for deal in deals:
                    self.backtest_launch_repo.add_backtest_deal(new_launch.id, deal["id"])
            else:
                deal = self.repository.get_deal_by_sell_order_id(close_orders[0]['orderId'])
                self.backtest_launch_repo.add_backtest_deal(new_launch.id, deal["id"])

            profit = self.backtest_result_repo.evaluate_result(new_launch.id, start_date, end_date)
            print(profit)
            self.backtest_result_repo.add_backtest_result(launch_id=new_launch.id, total_profit_loss=profit[0])
        else:
            print(f"There is no deals in the interval from {start_date} till {end_date}")

    def make_mock_order(self, closed_price, qty, start_interval, side):
        order = prepare_mock_order(self.order_id, start_interval, qty, closed_price, side)
        self.order_id += 1
        self.client.create_order = MagicMock(return_value=order)
        self.client.get_order = MagicMock(return_value=order)
        return order


def start_backtest(argv):
    backtest = StrategyBackTest()
    backtest.setUp()
    backtest.test_strategy()


if __name__ == '__main__':
    start_backtest(argv=['first-arg-is-ignored'] + unknown)
