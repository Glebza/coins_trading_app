from binance.enums import *
from decimal import *
from datetime import datetime, timedelta
import talib

LOWEST_PRICE_DEVIATION_RANGE = 3

PEAK_PRICE_TRESHOLD = 100

close_prices_index = 0
high_prices_index = 2
low_prices_index = 3
top_price = 0
bottom_price = 0
deviation_price = 0
warm_up_data = None
fibo = dict()
is_long_position = True
stop_loss = 0
peak_center_price = 0
peak_center_interval = None
lowest_low_low_price = 0
lowest_low_low_interval = None
point3_price = 0
point3_interval = None
fibo = []
from_top_to_down = True
sidewalk_search_countdown = 30


def prepare(args):
    print("there are no prerarations for this strategy")


def _build_fibonacci_retracement(high, low, is_top_to_down):
    high = Decimal(high)
    low = Decimal(low)
    diff = high - low
    fibonacci = dict()
    if is_top_to_down:
        fibonacci['fib1'] = round(Decimal(high), 5)
        fibonacci['fib786'] = round(Decimal(high - (diff * Decimal(0.705))), 5)
        fibonacci['fib50'] = round(Decimal(high - (diff * Decimal(0.5))), 5)
        fibonacci['fib236'] = round(Decimal(high - (diff * Decimal(0.295))), 5)
        fibonacci['fib0'] = round(Decimal(low), 5)
    else:
        fibonacci['fib1'] = round(Decimal(low), 5)
        fibonacci['fib786'] = round(Decimal(low + (diff * Decimal(0.705))), 5)
        fibonacci['fib50'] = round(Decimal(low + (diff * Decimal(0.5))), 5)
        fibonacci['fib236'] = round(Decimal(low + (diff * Decimal(0.295))), 5)
        fibonacci['fib0'] = round(Decimal(high), 5)

    return fibonacci


def _reset_sidewalk_indicators():
    global peak_center_interval
    global point3_interval
    global point3_price
    global peak_center_price
    global lowest_low_low_price
    global lowest_low_low_interval
    point3_price = 0
    point3_interval = None
    peak_center_price = 0
    lowest_low_low_price = 0
    lowest_low_low_interval = None


# пока только long позиции
def do_sidewalk_finding(prices, intervals):
    global peak_center_interval
    global point3_interval
    global point3_price
    global peak_center_price
    global lowest_low_low_price
    global lowest_low_low_interval
    global fibo
    global from_top_to_down
    global sidewalk_search_countdown
    high_prices = prices[1]
    low_prices = prices[2]
    low_price = low_prices[-1]
    high_price = high_prices[-1]
    if point3_price == 0:
        if peak_center_price == 0:
            peak_center_price = high_prices[-5]
            peak_center_interval = intervals[-5]
            is_a_peak = True
            for hg_p in high_prices[-4:-1]:
                if peak_center_price <= hg_p:
                    is_a_peak = False
            for hg_p in high_prices[-15:-5]:
                if peak_center_price <= hg_p:
                    is_a_peak = False
            if is_a_peak:
                is_big_left_range = peak_center_price - high_prices[-15] > PEAK_PRICE_TRESHOLD
                is_big_right_range = peak_center_price - low_price > PEAK_PRICE_TRESHOLD
                if is_big_left_range and is_big_right_range:
                    lowest_low_low_price = low_prices[-1]
                    lowest_low_low_interval = intervals[-1]
                else:
                    _reset_sidewalk_indicators()
            else:
                _reset_sidewalk_indicators()
        else:
            #check the equal high/lows and skip adjacent bars
            if (abs(lowest_low_low_price - low_price) <= LOWEST_PRICE_DEVIATION_RANGE
                    and intervals[-1] > lowest_low_low_interval + timedelta(minutes=1)):
                point3_price = low_price
                point3_interval = intervals[-1]
                from_top_to_down = True
            else:
                # find Lowest low (point 2 )
                if lowest_low_low_price > low_price:
                    lowest_low_low_price = low_price
                    lowest_low_low_interval = intervals[-1]
                elif abs(peak_center_price - high_price) <= 3:
                    point3_price = high_price
                    point3_interval = intervals[-1]
                    from_top_to_down = False
            sidewalk_search_countdown = sidewalk_search_countdown - 1
            if sidewalk_search_countdown == 0:
                _reset_sidewalk_indicators()
                sidewalk_search_countdown = 30
    else:
        fibo = dict()
        if from_top_to_down:
            fibo = _build_fibonacci_retracement(peak_center_price, point3_price, from_top_to_down)
        else:
            fibo = _build_fibonacci_retracement(point3_price, lowest_low_low_price, from_top_to_down)
        print("side walk detected: peak tm  {}. point2 tm {}. point3 tm {} ".format(
            peak_center_interval, lowest_low_low_interval, point3_interval
        ))
        print("side walk detected: fibo   {}. ".format(fibo))
        print("--------")
        _reset_sidewalk_indicators()

    return fibo


def process_sidewalk(prices, intervals, fibo):

    return None


def process(prices, intervals, order):
    close_prices = prices[0]
    high_prices = prices[1]
    low_prices = prices[2]
    global stop_loss
    global fibo
    track = dict({'action': 'WAIT', 'price': 0})
    close_price = close_prices[-1]
    low_price = low_prices[-1]
    high_price = high_prices[-1]

    fibo = do_sidewalk_finding(prices, intervals)
    if fibo and len(fibo) > 0 :
        #track = process_sidewalk(prices, intervals, fibo)
        #нужно добавить проверку на комиссию
        if order is not None and order['status'] == ORDER_STATUS_FILLED:
            if is_long_position:
                if (close_price <= stop_loss != 0) or close_price >= fibo['fib50']:
                    track = dict({'action': 'SELL', 'price': close_price})
                    fibo = None
            else:
                if close_price >= stop_loss or close_price <= fibo['fib50']:
                    track = dict({'action': 'BUY', 'price': close_price})

        else:
            #нужно реализовать работу когда фибу строим снизу-вверх
            if is_long_position:
                # buy if  the price returned into the range after the peak was happened
                if close_price < fibo['fib0']:
                    buy_price = close_prices[-1] + 0.1
                    #stop_loss = Decimal(buy_price) - (fibo['fib0'] - fibo['fib1'])
                    stop_loss = 100
                    print("stop loss {}".format(stop_loss))
                    track = dict({'action': 'BUY', 'price': buy_price})
            #нужно реализовать сигналы на шорт

    return track
