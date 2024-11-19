from binance.enums import *
from decimal import *
from datetime import datetime, timedelta
import logging

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)


class SideWalk:
    def __init__(self):
        self.fibo = dict()
        self.higher_high = 0
        self.higher_high_interval = None
        self.lower_lows = 0
        self.lower_lows_interval = None
        self.point3_price = 0
        self.point3_interval = None

    def get_fibo(self):
        return self.fibo

    def set_fibo(self, fibo):
        self.fibo = fibo

    def get_higher_high(self):
        return self.higher_high

    def set_higher_high(self, higher_high):
        self.higher_high = higher_high

    def get_higher_high_interval(self):
        return self.higher_high_interval

    def set_higher_high_interval(self, higher_high_interval):
        self.higher_high_interval = higher_high_interval

    def get_lower_lows(self):
        return self.lower_lows

    def set_lower_lows(self, lower_lows):
        self.lower_lows = lower_lows

    def get_lower_lows_interval(self):
        return self.lower_lows_interval

    def set_lower_lows_interval(self, lower_lows_interval):
        self.lower_lows_interval = lower_lows_interval

    def get_point3_price(self):
        return self.point3_price

    def set_point3_price(self, point3_price):
        self.point3_price = point3_price

    def get_point3_interval(self):
        return self.point3_interval

    def set_point3_interval(self, point3_interval):
        self.point3_interval = point3_interval

    def build_fibonacci_retracement(self):
        fibonacci = dict()
        if self.higher_high != 0 and self.lower_lows != 0:
            high = Decimal(self.higher_high)
            low = Decimal(self.lower_lows)
            diff = high - low
            fibonacci['fib1'] = round(Decimal(high), 5)
            fibonacci['fib786'] = round(Decimal(low + (diff * Decimal(0.786))), 5)
            fibonacci['fib50'] = round(Decimal(low + (diff * Decimal(0.5))), 5)
            fibonacci['fib236'] = round(Decimal(low + (diff * Decimal(0.295))), 5)
            fibonacci['fib0'] = round(Decimal(low), 5)

        self.fibo = fibonacci
        return self.fibo


class DeviationsStrategy:

    def __init__(self, config):
        """
                Initialize the strategy with a configuration object.

                :param config: dict containing strategy parameters such as thresholds and look-back periods.
                """

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.sidewalk = SideWalk()
        self.is_long_position = True

        # sidewalk searching parameters
        self.peak_range_in_candles = config.get('peak_range_in_candles', 4)
        self.look_back_period = config.get('look_back_period', 60)
        self.retest_price_error_rate = config.get('retest_price_error_rate', 10)
        self.lowest_price_error_range = config.get('lowest_price_error_range', 3)
        self.point3_price_error_rate= config.get('point3_price_error_rate', 3)
        self.min_range_from_base_to_peak= config.get('min_range_from_base_to_peak', 100)

        # sidewalk process parameters
        self.stop_loss = 0
        self.price_retest_the_fibo_level = 10
        self.is_returned_to_sidewalk = False
        self.deviation_price = 0

    def get_stop_loss(self):
        return self.stop_loss

    def prepare(self, args):
        print("there are no prerarations for this strategy")

    def _do_sidewalk_finding(self, prices, k_intervals):
        high_prices = prices[1]
        low_prices = prices[2]
        intervals = k_intervals
        low_price = low_prices[-1]
        window_size = self.look_back_period

        if len(high_prices) > window_size:
            high_prices = high_prices[-window_size:]
            low_prices = low_prices[-window_size:]
            intervals = intervals[-window_size:]

        peak_distance = self.peak_range_in_candles
        lower_low_commitment = False
        for i in range(peak_distance, len(high_prices) - peak_distance):
            if self.sidewalk.get_point3_price() == 0:
                if lower_low_commitment:
                    if self.sidewalk.get_lower_lows() == 0:
                        is_uptrend = all(high_prices[j] < high_prices[j + 1] for j in range(i - peak_distance, i))
                        is_downtrend = all(high_prices[j] > high_prices[j + 1] for j in range(i, i + peak_distance))
                        base_to_peak_move = high_prices[i] - min(low_prices[i - peak_distance:i])
                        is_valid_peak_move = base_to_peak_move >= self.min_range_from_base_to_peak
                        if is_uptrend and is_downtrend and is_valid_peak_move:
                            # Find the lowest price on the right side of the peak
                            right_side_low = min(low_prices[i + 1:i + 1 + peak_distance])
                            right_side_low_index = low_prices[i + 1:i + 1 + peak_distance].index(right_side_low) + i + 1
                            # Record the swing high and its properties
                            # check the peak and lows bars are not adjacent
                            if abs(right_side_low_index - i) > 1:
                                self.sidewalk.set_higher_high(high_prices[i])
                                self.sidewalk.set_higher_high_interval(intervals[i])
                                self.sidewalk.set_lower_lows(right_side_low)
                                self.sidewalk.set_lower_lows_interval(intervals[right_side_low_index])
                    else:
                        # check if the bars continued to go down
                        if self.sidewalk.get_lower_lows() < low_price and not self.lower_low_commitment:
                            self.sidewalk.set_lower_lows(low_price)
                            self.sidewalk.set_lower_lows_interval(intervals[-1])
                        else:
                            self.lower_low_commitment = True

                else:
                    if high_prices[-1] > self.sidewalk.get_higher_high():
                        lower_low_commitment = False
                        self.sidewalk = SideWalk()

                    elif (abs(self.sidewalk.get_lower_lows() - low_price) <= self.lowest_price_error_range
                            and intervals[-1] > self.sidewalk.get_lower_lows_interval() + timedelta(minutes=1)):
                        self.sidewalk.set_point3_price(low_price)
                        self.sidewalk.set_point3_interval(intervals[-1])

            else:
                fibo = self.sidewalk.build_fibonacci_retracement()
                print("side walk detected: peak tm  {}. point2 tm {}. point3 tm {} ".format(
                    self.sidewalk.get_higher_high_interval(), self.sidewalk.get_lower_lows_interval(),
                    self.sidewalk.get_point3_interval()
                ))
                print("side walk detected: fibo   {}. ".format(fibo))
                print("--------")

        return self.sidewalk

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
                    self.reset_sidewalk_points()
            else:
                if close_price >= self.stop_loss or close_price <= self.fibo['fib50']:
                    track = dict({'action': 'BUY', 'price': close_price})

        else:

            if low_price < self.fibo['fib0']:
                if self.is_returned_to_sidewalk and low_price < self.lower_lows:
                    self.reset_sidewalk_points()
                    self.fibo = None
                    return track
                elif self.deviation_price == 0 or low_price <= self.deviation_price:
                    self.deviation_price = low_price
            # check whether the price left the fibonacci retracement
            elif low_price > self.fibo['fib1']:
                self.reset_sidewalk_points()
                self.fibo = 0
                return track

            # wait until the price returns and retests the fib0 level
            if self.deviation_price != 0 and self.fibo['fib0'] <= low_price <= self.fibo['fib236']:
                self.is_returned_to_sidewalk = True

            if self.is_long_position:
                # buy if  the price returned into the range after the peak was happened
                if self.is_returned_to_sidewalk and abs(low_price - self.fibo['fib0']) <= self.price_retest_the_fibo_level:
                    buy_price = close_prices[-1] + 0.1
                    self.stop_loss = Decimal(self.deviation_price - 1)
                    print("stop loss {}".format(self.stop_loss))
                    track = dict({'action': 'BUY', 'price': buy_price})
                    self.is_returned_to_sidewalk = False
                    self.deviation_price = 0

        return track

    def process(self, prices, intervals, order):

        track = dict({'action': 'WAIT', 'price': 0})

        if self.fibo and len(self.fibo) > 0:
            track = self.process_sidewalk(prices, order, track)
        else:
            self.fibo = self._do_sidewalk_finding(prices, intervals)

        return track
