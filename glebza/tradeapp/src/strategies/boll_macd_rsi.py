import talib
import numpy
from talib import MA_Type
from binance.enums import *

DEAL_DEADLINE_MILLISECONDS = 120000

PROFIT_RATE = 15

RSI_OVERSOLD = 50

RSI_PERIOD = 15


def prepare(args):
    print('strategy doesn\'t need additional preparations')


def process(prices, current_interval, order):
    close_prices = prices[0]
    track = dict({'action': 'WAIT', 'price': 0})
    # Делаем своеобразный наивный прогноз, что следующая цена не будет отличаться.
    # Так мы можем попытаться предсказать пересечет ли MACD линию Sygnal.
    # Это позволит немного опередить ботов и возможно купить дешевле
    np_closes = numpy.append(numpy.array(close_prices), close_prices[-1])
    rsi = talib.RSI(np_closes, RSI_PERIOD)
    macd, signal, macd_diff = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)
    upper, middle, lower = talib.BBANDS(numpy.array(close_prices), timeperiod=21, matype=MA_Type.T3)

    if order is not None and order['status'] == ORDER_STATUS_FILLED:
        if (float(close_prices[-1]) > float(order['price'])) or \
                (macd[-1] < signal[-1] and macd[-2] >= signal[-2]):
                #current_interval - order['time'] >= DEAL_DEADLINE_MILLISECONDS or\

            track = dict({'action': 'SELL', 'price': close_prices[-1]})
    else:
        if rsi[-1] < RSI_OVERSOLD and macd[-1] > signal[-1] and macd[-2] <= signal[-2] and macd[-1] < 0:
            close_price = close_prices[-1]
            buy_price = close_price + 0.1
            track = dict({'action': 'BUY', 'price': buy_price})

    return track

#(float(close_prices[-1]) - float(order['price'])) >= PROFIT_RATE
#(float(order['price']) - float(close_prices[-1])) >= 64 or \
#current_interval - order['time'] >= DEAL_DEADLINE_MILLISECONDS: