from binance.enums import *
from decimal import *

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


def prepare(args):
    global is_long_position
    global fibo
    global stop_loss
    high_prices = args[high_prices_index]
    low_prices = args[low_prices_index]
    top_price = Decimal(max(high_prices))
    top_index = high_prices.index(top_price)
    bottom_price = Decimal(min(low_prices))
    bottom_index = low_prices.index(bottom_price)
    if top_index > bottom_index:
        is_long_position = False

        fibo = _build_fibonacci_retracement(top_price, bottom_price, is_long_position)

    else:
        is_long_position = True

        fibo = _build_fibonacci_retracement(top_price, bottom_price, is_long_position)


def _build_fibonacci_retracement(high, low, is_long_position):
    diff = high - low
    fibonacci = dict()
    if is_long_position:
        fibonacci['fib786'] = Decimal(low + (diff * Decimal(0.786)))
        fibonacci['fib618'] = Decimal(low + (diff * Decimal(0.618)))
        fibonacci['fib50'] = Decimal(low + (diff * Decimal(0.5)))
        fibonacci['fib382'] = Decimal(low + (diff * Decimal(0.382)))
        fibonacci['fib236'] = Decimal(low + (diff * Decimal(0.236)))
    else:
        fibonacci['fib786'] = Decimal(high - (diff * Decimal(0.786)))
        fibonacci['fib618'] = Decimal(high - (diff * Decimal(0.618)))
        fibonacci['fib50'] = Decimal(high - (diff * Decimal(0.5)))
        fibonacci['fib382'] = Decimal(high - (diff * Decimal(0.382)))
        fibonacci['fib236'] = Decimal(high - (diff * Decimal(0.236)))
    return fibonacci


# пока только long позиции
def process(prices, current_interval, order):
    close_prices = prices[0]
    high_prices = prices[1]
    low_prices = prices[2]
    global deviation_price
    global stop_loss
    track = dict({'action': 'WAIT', 'price': 0})
    close_price = close_prices[-1]
    if order is not None and order['status'] == ORDER_STATUS_FILLED:
        if is_long_position:
            if (close_price <= stop_loss != 0) or close_price >= fibo['fib50']:
                track = dict({'action': 'SELL', 'price': close_price})
        else:
            if close_price >= stop_loss or close_price <= fibo['fib50']:
                track = dict({'action': 'BUY', 'price': close_price})

    else:
        if is_long_position:
            # buy if  the price returned into the range after the peak was happened
            if deviation_price != 0 and low_prices[-1] >= bottom_price:
                buy_price = close_prices[-1] + 0.1
                stop_loss = deviation_price - deviation_price * Decimal(0.01)
                track = dict({'action': 'BUY', 'price': buy_price})
        else:
            if deviation_price != 0 and high_prices[-1] <= top_price:
                stop_loss = deviation_price + deviation_price * Decimal(0.01)
                track = dict({'action': 'SELL', 'price': close_price})

    if Decimal(high_prices[-1]) > top_price:
        deviation_price = close_price
    if Decimal(low_prices[-1]) < bottom_price:
        deviation_price = close_price

    return track
