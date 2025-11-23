import numpy as np
import tulipy as ti
from binance.enums import *
from datetime import datetime


class BollMacdRsiStrategy:

    def __init__(self):
        self.deal_deadline_ms = 120000  # 2 minutes
        self.rsi_period = 15
        self.rsi_oversold = 30
        self.macd_fast = 6
        self.macd_slow = 13
        self.macd_signal = 5
        self.bbands_period = 21
        self.take_profit_rate = 0.007  # 0.7%
        self.stop_loss_rate = 0.005  # 0.5%

    def prepare(self, args):
        self.deal_deadline_ms = args['deal_deadline_ms']
        self.rsi_period = args['rsi_period']
        self.rsi_oversold = args['rsi_oversold']
        self.macd_fast = args['macd_fast']
        self.macd_slow = args['macd_slow']
        self.macd_signal = args['macd_signal']
        self.bbands_period = args['bbands_period']
        self.take_profit_rate = args['take_profit_rate']
        self.stop_loss_rate = args['stop_loss_rate']

    def process(self, prices, intervals, order):
        close_prices = prices[0]
        track = {'action': 'WAIT', 'price': 0}
        np_closes = np.array(close_prices)
        # Append the last price to predict the next movement
        np_closes = np.append(np_closes, close_prices[-1])
        # Check there's enough data for each indicator calculation
        if len(np_closes) < max(self.rsi_period, self.bbands_period, self.macd_slow):
            print("Not enough data for indicators")
            return track

        rsi = ti.rsi(np_closes, period=self.rsi_period)
        macd, signal, macd_hist = ti.macd(np_closes, short_period=self.macd_fast, long_period=self.macd_slow,
                                          signal_period=self.macd_signal)
        upper, middle, lower = ti.bbands(np_closes[:-1], period=self.bbands_period, stddev=2)
        current_price = close_prices[-1]

        if order is not None and order['status'] == ORDER_STATUS_FILLED:
            entry_price = float(order['price'])
            pnl = (current_price - entry_price) / entry_price
            current_interval = intervals[-1]
            age = current_interval - order['transacttime']
            if (pnl >= self.take_profit_rate or
                    pnl <= -self.stop_loss_rate or
                    age.total_seconds()*1000 >= self.deal_deadline_ms or
                    (macd[-1] < signal[-1] and macd[-2] >= signal[-2])):
                print(
                    f"DEBUG: pnl = {pnl}. age = {age}. macd[-1] = {macd[-1]} signal[-1] = {signal[-1]}. macd[-2] = {macd[-2]} signal[-2] = {signal[-2]}.")
                track = {'action': 'SELL', 'price': current_price}

        elif order is None:
            if (rsi[-1] < self.rsi_oversold
                    and macd[-1] > signal[-1] and macd[-2] <= signal[-2]  # MACD bull cross
                    and current_price < middle[-1]):  # below Bollinger midline
                buffer = current_price * 0.001  # dynamic price buffer ~0.1%
                track = {'action': 'BUY', 'price': round(current_price + buffer, 6)}

        return track
