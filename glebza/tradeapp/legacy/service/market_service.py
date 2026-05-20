import logging
from datetime import datetime, timedelta
from decimal import *


def get_transformed_klines(client, symbol, timeframe, interval="1 day ago UTC", interval_end=None):
    logging.info(symbol)
    volumes = []
    closes = []
    high_prices = []
    low_prices = []
    open_prices = []
    intervals = []
    klines = client.get_historical_klines(symbol, timeframe, interval, interval_end)
    start_interval = 0
    open_p = 1
    high = 2
    low = 3
    close = 4
    volume = 5
    for kline in klines:
        closes.append(float(kline[close]))
        volumes.append(float(kline[volume]))
        high_prices.append(float(kline[high]))
        low_prices.append(float(kline[low]))
        open_prices.append(float(kline[open_p]))
        intervals.append(kline[start_interval])
    return closes, volumes, high_prices, low_prices, open_prices, intervals


def get_klines(client, symbol, timeframe, interval="1 day ago UTC", interval_end=None):
    klines = client.get_historical_klines(symbol, timeframe, interval, interval_end)
    return klines
