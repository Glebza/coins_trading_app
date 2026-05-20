import logging
import argparse

from glebza.tradeapp.tests.backtest.test_strategies import StrategyBackTest
from glebza.tradeapp.src.strategies.deviations import DeviationsStrategy
from glebza.tradeapp.src.strategies.boll_macd_rsi import BollMacdRsiStrategy
from glebza.tradeapp.tests.backtest.repository.backtest_launch_repository import BacktestLaunchRepository
from glebza.tradeapp.tests.backtest.repository.strategy_repository import StrategyRepository

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
        self.args, self.unknown = self.parser.parse_known_args()
        self.backtest_launch_repo = BacktestLaunchRepository()
        self.strategy_repository = StrategyRepository()

    def start_test_cycle(self):
        args, unknown = self.parser.parse_known_args()
        strategy_name = args.strategy_name

        if strategy_name == "boll_macd_rsi":
            strategy = BollMacdRsiStrategy()
            strategy_id = self.strategy_repository.get_strategy_by_title(strategy_name)
            config = {
                'deal_deadline_ms': 120000,
                'rsi_period': 15,
                'rsi_oversold': 30,
                'macd_fast': 6,
                'macd_slow': 13,
                'macd_signal': 5,
                'bbands_period': 21,
                'take_profit_rate': 0.005,
                'stop_loss_rate': 0.001,

            }
            # step config parameter : {min value, max value, step }
            step_config = {
                'rsi_oversold': [25, 45, 5],
                'take_profit_rate': [0.005, 0.025, 0.005],
                'stop_loss_rate': [0.001, 0.021, 0.005],
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

        for key, val in step_config.items():
            current_parameter_value = val[0]
            while current_parameter_value <= val[1]:
                config[key] = current_parameter_value
                #self.backtest_launch_repo.add_backtest_strategy_detail(strategy_id=strategy_id,)
                print(f'current config = {config}')
                strategy.prepare(config)
                back_test = StrategyBackTest(strategy, args)
                back_test.test_strategy()
                current_parameter_value += val[2]


if __name__ == '__main__':
    launcher = BacktestLauncher()
    launcher.start_test_cycle()

