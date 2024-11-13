import logging
from datetime import datetime, timedelta

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)

def warm_up(self, backtest_repository, kline_interval, backtest_start_date):
    logging.info(self.symbol)
    intervals = []
    volumes = []
    closes = []
    lows = []
    highs = []
    start_date = datetime.strptime(backtest_start_date, "%d.%m.%Y %H:%M:%S")
    end_date = None
    if kline_interval == "1m":
        end_date = (start_date + timedelta(hours=1)).strftime("%d.%m.%Y %H:%M:%S")
    if kline_interval == "1h":
        end_date = (start_date + timedelta(days=1)).strftime("%d.%m.%Y %H:%M:%S")
    # start_date = datetime(2024, 10, 10, 18, 34, 0)
    # end_date = datetime(2024, 10, 10, 19, 34, 59)
    klines = backtest_repository.get_historical_klines(start_date, end_date, self.symbol, kline_interval)
    start_interval = 0
    open_p = 1
    high = 2
    low = 3
    close = 4
    volume = 5
    for kline in klines:
        intervals.append(kline[start_interval])
        volumes.append(kline[volume])
        closes.append(float(kline[close]))
        lows.append(float(kline[low]))
        highs.append(float(kline[high]))

    print('warm up data received')
    return closes, volumes, highs, lows, intervals


def prepare_mock_order(order_id, time, qty, close_price, side):
        order = dict(
            {'symbol': 'BTCUSDT',
             'orderId': order_id,
             'orderListId': -1,
             'clientOrderId': 'bU2iE4DQGRsUP7euHmw5QE',
             'price': close_price,
             'origQty': qty,
             'executedQty': qty,
             'cummulativeQuoteQty': '530.00616000',
             'status': 'FILLED',
             'timeInForce': 'FOK',
             'type': 'LIMIT',
             'side': side,
             'stopPrice': '0.00000000', 'icebergQty': '0.00000000',
             'time': time,
             'updateTime': 1674685872599, 'isWorking': True, 'workingTime': 1674685872599,
             'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'NONE'})

        self.order_id = self.order_id + 1

        return order