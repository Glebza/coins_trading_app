import logging
from datetime import datetime, timedelta


def warm_up(client, symbol, interval="1 day ago UTC"):
    logging.info(symbol)
    volumes = []
    closes = []
    klines = client.get_historical_klines(symbol, client.KLINE_INTERVAL_1MINUTE, interval)
    start_interval = 0
    open_p = 1
    high = 2
    low = 3
    close = 4
    volume = 5
    for kline in klines:
        volumes.append(float(kline[volume]))
        closes.append(float(kline[close]))
    return closes, volumes