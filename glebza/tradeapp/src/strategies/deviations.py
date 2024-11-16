from binance.enums import *
from decimal import *
from datetime import datetime, timedelta
import logging

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)


class DeviationsStrategy:

    def __init__(self, config):
        """
                Initialize the strategy with a configuration object.

                :param config: dict containing strategy parameters such as thresholds and look-back periods.
                """
        self.deviation_threshold = config.get('deviation_threshold', 1.5)
        self.look_back_period = config.get('look_back_period', 20)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(config.get('log_level', logging.INFO))

        self.close_prices_index = 0
        self.high_prices_index = 2
        self.low_prices_index = 3
        self.top_price = 0
        self.bottom_price = 0
        self.deviation_price = 0
        self.fibo = dict()
        self.is_long_position = True
        self.stop_loss = 0
        self.peak_center_price = 0
        self.peak_center_interval = None
        self.lowest_low_low_price = 0
        self.lowest_low_low_interval = None
        self.point3_price = 0
        self.point3_interval = None
        self.sidewalk_search_countdown = 30
        self.is_returned_to_sidewalk = False
        self.LOWEST_PRICE_DEVIATION_RANGE = 3
        self.PEAK_PRICE_THRESHOLD = 100

    def get_stop_loss(self):
        return self.stop_loss

    def prepare(self, args):
        print("there are no prerarations for this strategy")

    def _build_fibonacci_retracement(self, high, low):
        high = Decimal(high)
        low = Decimal(low)
        diff = high - low
        fibonacci = dict()
        fibonacci['fib1'] = round(Decimal(high), 5)
        fibonacci['fib786'] = round(Decimal(high - (diff * Decimal(0.705))), 5)
        fibonacci['fib50'] = round(Decimal(high - (diff * Decimal(0.5))), 5)
        fibonacci['fib236'] = round(Decimal(high - (diff * Decimal(0.295))), 5)
        fibonacci['fib0'] = round(Decimal(low), 5)
        self.fibo = fibonacci

        return self.fibo

    def _reset_sidewalk_indicators(self):
        self.point3_price = 0
        self.point3_interval = None
        self.peak_center_price = 0
        self.lowest_low_low_price = 0
        self.lowest_low_low_interval = None

    def _do_sidewalk_finding(self, prices, intervals):
        high_prices = prices[1]
        low_prices = prices[2]
        low_price = low_prices[-1]
        high_price = high_prices[-1]
        if self.point3_price == 0:
            if self.peak_center_price == 0:
                self.peak_center_price = high_prices[-4]
                self.peak_center_interval = intervals[-4]
                is_a_peak = True
                for hg_p in high_prices[-3:-1]:
                    if self.peak_center_price <= hg_p:
                        is_a_peak = False
                for hg_p in high_prices[-15:-5]:
                    if self.peak_center_price <= hg_p:
                        is_a_peak = False
                if is_a_peak:
                    is_big_left_range = self.peak_center_price - high_prices[-15] > self.PEAK_PRICE_THRESHOLD
                    is_big_right_range = self.peak_center_price - low_price > self.PEAK_PRICE_THRESHOLD
                    if is_big_left_range and is_big_right_range:
                        self.lowest_low_low_price = low_prices[-1]
                        self.lowest_low_low_interval = intervals[-1]
                    else:
                        self._reset_sidewalk_indicators()
                else:
                    self._reset_sidewalk_indicators()
            else:
                # check the equal high/lows and skip adjacent bars
                if (abs(self.lowest_low_low_price - low_price) <= self.LOWEST_PRICE_DEVIATION_RANGE
                        and intervals[-1] > self.lowest_low_low_interval + timedelta(minutes=1)):
                    self.point3_price = low_price
                    self.point3_interval = intervals[-1]

                else:
                    # find Lowest low (point 2 )
                    if self.lowest_low_low_price > low_price:
                        self.lowest_low_low_price = low_price
                        self.lowest_low_low_interval = intervals[-1]
                    elif abs(self.peak_center_price - high_price) <= 3:
                        self.point3_price = high_price
                        self.point3_interval = intervals[-1]
                self.sidewalk_search_countdown -= 1
                if self.sidewalk_search_countdown == 0:
                    self._reset_sidewalk_indicators()
                    self.sidewalk_search_countdown = 30
        else:
            self.fibo = self._build_fibonacci_retracement(self.peak_center_price, self.lowest_low_low_price)
            print("side walk detected: peak tm  {}. point2 tm {}. point3 tm {} ".format(
                self.peak_center_interval, self.lowest_low_low_interval, self.point3_interval
            ))
            print("side walk detected: fibo   {}. ".format(self.fibo))
            print("--------")
            self._reset_sidewalk_indicators()

        return self.fibo

    def process_sidewalk(self, prices, order, track):
        close_prices = prices[0]
        low_prices = prices[2]
        close_price = Decimal(close_prices[-1])
        low_price = Decimal(low_prices[-1])

        if order is not None and order['status'] == ORDER_STATUS_FILLED:
            if self.is_long_position:
                if (close_price <= self.stop_loss != 0) or close_price >= self.fibo['fib786']:
                    track = dict({'action': 'SELL', 'price': close_price})
                    self.fibo = None
                    self.deviation_price = 0
                    self.stop_loss = 0
            else:
                if close_price >= self.stop_loss or close_price <= self.fibo['fib50']:
                    track = dict({'action': 'BUY', 'price': close_price})

        else:
            if low_price < self.fibo['fib0']:
                if self.deviation_price == 0 or low_price <= self.deviation_price:
                    self.deviation_price = low_price

            if self.deviation_price != 0 and self.fibo['fib0'] <= low_price <= self.fibo['fib50']:
                self.is_returned_to_sidewalk = True

            if self.is_long_position:
                # buy if  the price returned into the range after the peak was happened
                if self.is_returned_to_sidewalk and low_price <= self.fibo['fib0'] and abs(
                        low_price - self.fibo['fib0']) <= 3:
                    buy_price = close_prices[-1] + 0.1
                    self.stop_loss = Decimal(self.deviation_price - 1)
                    print("stop loss {}".format(self.stop_loss))
                    track = dict({'action': 'BUY', 'price': buy_price})

                    self.is_returned_to_sidewalk = False
                    self.deviation_price = 0
        return track

    def process(self, prices, intervals, order):

        track = dict({'action': 'WAIT', 'price': 0})
        self.fibo = self._do_sidewalk_finding(prices, intervals)
        if self.fibo and len(self.fibo) > 0:
            track = self.process_sidewalk(prices, order, track)

        return track
