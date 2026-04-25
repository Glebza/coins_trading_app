import numpy as np
import tulipy as ti
from binance.enums import *

from glebza.tradeapp.src.framework.forecasts import FORECAST_CAP, combine_weighted_forecasts


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
        # Carver-style rule weights (sum to 1); combined forecast is capped at ±FORECAST_CAP.
        self.forecast_weights = {"rsi": 0.35, "macd": 0.40, "bbands": 0.25}

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
        if "forecast_weights" in args and args["forecast_weights"]:
            self.forecast_weights = dict(args["forecast_weights"])

    def _forecast_rsi(self, rsi_last: float) -> float:
        """Oversold → positive forecast; overbought → negative (roughly ±10)."""
        if rsi_last < self.rsi_oversold:
            return 10.0 * (self.rsi_oversold - rsi_last) / max(self.rsi_oversold, 1e-9)
        if rsi_last > 70.0:
            return -10.0 * (rsi_last - 70.0) / 30.0
        return 0.0

    def _forecast_macd(self, macd, signal) -> float:
        """Cross and trend vs signal line (roughly ±10)."""
        if len(macd) < 2 or len(signal) < 2:
            return 0.0
        diff = float(macd[-1] - signal[-1])
        prev_diff = float(macd[-2] - signal[-2])
        cross = 0.0
        if prev_diff <= 0.0 < diff:
            cross = 8.0
        elif prev_diff >= 0.0 > diff:
            cross = -8.0
        denom = abs(float(signal[-1])) + 1e-12
        trend = float(np.clip((diff / denom) * 5.0, -5.0, 5.0))
        return float(np.clip(cross + trend, -10.0, 10.0))

    def _forecast_bbands(self, current_price: float, middle_last: float) -> float:
        """Below midline → positive mean-reversion tilt (roughly ±10)."""
        if middle_last <= 0:
            return 0.0
        rel = (middle_last - current_price) / middle_last
        return float(np.clip(rel * 20.0, -10.0, 10.0))

    def _compute_forecast_components(
        self, rsi, macd, signal, current_price: float, middle
    ) -> dict:
        rsi_last = float(rsi[-1])
        mid_last = float(middle[-1])
        return {
            "rsi": self._forecast_rsi(rsi_last),
            "macd": self._forecast_macd(macd, signal),
            "bbands": self._forecast_bbands(current_price, mid_last),
        }

    def process(self, prices, intervals, order):
        close_prices = prices[0]
        track = {
            "action": "WAIT",
            "price": 0,
            "forecast": 0.0,
            "forecast_components": {},
            "forecast_cap": FORECAST_CAP,
        }
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

        components = self._compute_forecast_components(rsi, macd, signal, current_price, middle)
        track["forecast_components"] = components
        track["forecast"] = combine_weighted_forecasts(components, self.forecast_weights, cap=FORECAST_CAP)

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
                track["action"] = "SELL"
                track["price"] = current_price

        elif order is None:
            if (rsi[-1] < self.rsi_oversold
                    and macd[-1] > signal[-1] and macd[-2] <= signal[-2]  # MACD bull cross
                    and current_price < middle[-1]):  # below Bollinger midline
                buffer = current_price * 0.001  # dynamic price buffer ~0.1%
                track["action"] = "BUY"
                track["price"] = round(current_price + buffer, 6)

        return track
