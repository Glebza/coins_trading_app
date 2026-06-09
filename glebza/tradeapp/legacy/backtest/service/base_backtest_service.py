import logging
import datetime

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)


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
         'transacttime': datetime.datetime.fromtimestamp(time),
         'updateTime': 1674685872599, 'isWorking': True, 'workingTime': 1674685872599,
         'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'NONE'})
    return order
