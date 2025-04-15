import numpy as np
import tulipy as ti
from binance.enums import *
from datetime import datetime
DEAL_DEADLINE_MILLISECONDS = 120000

# Configuration
DEAL_DEADLINE_MS = 120000  # 2 minutes
RSI_PERIOD = 15
RSI_OVERSOLD = 30
MACD_FAST = 6
MACD_SLOW = 13
MACD_SIGNAL = 5
BBANDS_PERIOD = 21
TAKE_PROFIT_RATE = 0.007  # 0.7%
STOP_LOSS_RATE = 0.005  # 0.5%


def prepare(args):
    profit_rate = args["profit_rate"]
    print("strategy doesn't need additional preparations")


def process(prices, intervals, order):
    close_prices = prices[0]
    track = {'action': 'WAIT', 'price': 0}

    # Ensure numpy array
    np_closes = np.array(close_prices)

    # Append the last price to predict the next movement
    np_closes = np.append(np_closes, close_prices[-1])

    # Check there's enough data for each indicator calculation
    if len(np_closes) < max(RSI_PERIOD, BBANDS_PERIOD, MACD_SLOW):
        print("Not enough data for indicators")
        return track

    # RSI using tulipy
    rsi = ti.rsi(np_closes, period=RSI_PERIOD)

    # MACD using tulipy
    macd, signal, macd_hist = ti.macd(np_closes, short_period=MACD_FAST, long_period=MACD_SLOW,
                                      signal_period=MACD_SIGNAL)

    # Bollinger Bands using tulipy
    upper, middle, lower = ti.bbands(np_closes[:-1], period=BBANDS_PERIOD, stddev=2)

    current_price = close_prices[-1]

    if order is not None and order['status'] == ORDER_STATUS_FILLED:
        entry_price = float(order['price'])
        pnl = (current_price - entry_price) / entry_price
        current_interval = intervals[-1]
        age = current_interval - order['transacttime']
        if (pnl >= TAKE_PROFIT_RATE or
                pnl <= -STOP_LOSS_RATE or
                datetime.timestamp(age) >= DEAL_DEADLINE_MS or
                (macd[-1] < signal[-1] and macd[-2] >= signal[-2])):
            print(
                f"DEBUG: pnl = {pnl}. age = {age}. macd[-1] = {macd[-1]} signal[-1] = {signal[-1]}. macd[-2] = {macd[-2]} signal[-2] = {signal[-2]}.")
            track = {'action': 'SELL', 'price': current_price}

    elif order is None:
        if (rsi[-1] < RSI_OVERSOLD
                and macd[-1] > signal[-1] and macd[-2] <= signal[-2]  # MACD bull cross
                and current_price < middle[-1]):  # below Bollinger midline
            buffer = current_price * 0.001  # dynamic price buffer ~0.1%
            track = {'action': 'BUY', 'price': round(current_price + buffer, 6)}

    return track
