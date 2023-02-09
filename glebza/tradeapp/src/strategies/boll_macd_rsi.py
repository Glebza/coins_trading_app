import talib
import numpy

PROFIT_RATE = 8
LOSE_RATE = -10
RSI_OVERSOLD = 51
RSI_PERIOD = 15


def process(close_prices, order):
    track = dict({'action': 'WAIT', 'price': 0})
    np_closes = numpy.append(numpy.array(close_prices),close_prices[-1])
    rsi = talib.RSI(np_closes, RSI_PERIOD)
    macd, signal, macd_diff = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)

    if order:
        if (float(close_prices[-1]) - float(order['price'])) >= PROFIT_RATE \
                or (macd[-1] < signal[-1] and macd[-2] >= signal[-2]):
            track = dict({'action': 'SELL', 'price': close_prices[-1]})
    else:
        if rsi[-1] < RSI_OVERSOLD and macd[-1] > signal[-1] and macd[-2] <= signal[-2] and macd[-1] < 0:
            close_price = close_prices[-1]
            buy_price = close_price + 0.1
            track = dict({'action': 'BUY', 'price': buy_price})

    return track

#   or (float(close_prices[-1]) - float(order['price'])) <= LOSE_RATE \