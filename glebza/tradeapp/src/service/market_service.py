import logging
from datetime import datetime, timedelta


def warm_up(client, symbol, interval="1 day ago UTC", interval_end=None):
    logging.info(symbol)
    volumes = []
    closes = []
    high_prices = []
    low_prices = []
    klines = client.get_historical_klines(symbol, client.KLINE_INTERVAL_1MINUTE, interval, interval_end)
    start_interval = 0
    open_p = 1
    high = 2
    low = 3
    close = 4
    volume = 5
    for kline in klines:
        volumes.append(float(kline[volume]))
        closes.append(float(kline[close]))
        high_prices.append(float(kline[high]))
        low_prices.append(float(kline[low]))
    return closes, volumes,high_prices, low_prices
