import logging
import os
import argparse

from glebza.tradeapp.tests.backtest.test_strategies import StrategyBackTest
from glebza.tradeapp.src.strategies.deviations import DeviationsStrategy
import glebza.tradeapp.src.strategies.boll_macd_rsi as boll_macd_rsi

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)


class BacktestLauncher:
    def __init__(self):
        self.parser = argparse.ArgumentParser(description="Run tests with custom arguments")
        self.parser.add_argument('--kline_interval', type=str, help='1m or 1h ')
        self.parser.add_argument('--backtest_start_date', type=str, help='dd.mm.yyyy hh24:Mi:ss')
        self.parser.add_argument('--backtest_end_date', type=str, help='dd.mm.yyyy hh24:Mi:ss')
        self.parser.add_argument('--backtest_interval', type=str, help='month or day or year')
        self.parser.add_argument('--start_cash', type=int, help='start money for trading')
        self.parser.add_argument('--symbol', type=str, help='BTCUSDT or else')
        self.parser.add_argument('--strategy_name', type=str, help='trading strategy')

    def start_test_cycle(self):
        args, unknown = self.parser.parse_known_args()
        kline_interval = args.kline_interval
        backtest_start_date = args.backtest_start_date
        backtest_end_date = args.backtest_end_date
        start_cash = args.start_cash
        symbol = args.symbol
        backtest_interval = args.backtest_interval
        strategy_name = args.strategy_name

        if strategy_name == "ball_macd_rsi":
            strategy = boll_macd_rsi
            config = {
                'DEAL_DEADLINE_MS': 120000,
                'RSI_PERIOD': 15,
                'RSI_OVERSOLD': 30,
                'MACD_FAST': 6,
                'MACD_SLOW': 13,
                'MACD_SIGNAL': 5,
                'BBANDS_PERIOD': 21,
                'TAKE_PROFIT_RATE': 0.005,
                'STOP_LOSS_RATE': 0.001,

            }
            # step config parameter : {min value, max value, step }
            step_config = {
                'RSI_OVERSOLD': [25, 45, 5],
                'TAKE_PROFIT_RATE': [0.005, 0.025, 0.005],
                'STOP_LOSS_RATE': [0.001, 0.021, 0.005],
            }
        else:

            config = {
                'peak_range_in_candles': 4,
                'look_back_period': 20,
                'retest_price_error_rate': 10,
                'lowest_price_error_range': 3,
                'point3_price_error_rate': 3,
                'min_range_from_base_to_peak': 100,
            }
            strategy = DeviationsStrategy(config)
            step_config = None

        for key, val in step_config:
            current_parameter_value = val[0]
            while current_parameter_value < val[1]:
                config[key] = current_parameter_value
                strategy.prepare(config)
                back_test = StrategyBackTest(strategy)
                back_test.test_strategy()
                current_parameter_value += val[2]


if __name__ == '__main__':
    start_backtest(argv=['first-arg-is-ignored'] + unknown)
