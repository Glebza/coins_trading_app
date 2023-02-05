import talib
import numpy

PROFIT_RATE = 8
RSI_OVERSOLD = 51
RSI_PERIOD = 15


def process(close_prices):
    track = 'WAIT', 0, 0, 0
    np_closes = numpy.array(close_prices)
    rsi = talib.RSI(np_closes, RSI_PERIOD)
    macd, signal, macd_diff = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)

    if rsi[-2] < RSI_OVERSOLD \
            and macd[-1] > signal[-1] and macd[-2] <= signal[-2] and macd[-1] < 0:
        close_price = close_prices[-1]
        buy_price = close_price + 0.1
        sell_price = buy_price + PROFIT_RATE
        lose_price = close_price - 5 * PROFIT_RATE
        track = 'BUY', buy_price, sell_price, lose_price

    return track
