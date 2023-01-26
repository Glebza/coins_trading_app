import unittest
from unittest.mock import MagicMock
from repository.binance_bot_repository import BinanceBotRepository
import datetime


class MyTestCase(unittest.TestCase):

    def setUp(self):
        self.repository = BinanceBotRepository()

    def test_save_order(self):
        binance_order = dict(
            {'symbol': 'BTCUSDT', 'orderId': 17811919231, 'orderListId': -1,
             'clientOrderId': 'ios_80b2f1a144b049308c7702da46ae2358', 'price': '23157.64000000',
             'origQty': '0.02260000', 'executedQty': '0.02260000', 'cummulativeQuoteQty': '523.36266400',
             'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'SELL', 'stopPrice': '0.00000000',
             'icebergQty': '0.00000000', 'time': 1674712111618, 'updateTime': 1674712120546, 'isWorking': True,
             'workingTime': 1674712111618, 'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'NONE'})
        self.repository.save_order(binance_order)
        target_order = dict({'clientorderid': 'ios_80b2f1a144b049308c7702da46ae2358',
                             'executedqty': 0.0226,
                             'id': 17811919231,
                             'orderlistid': -1,
                             'origqty': 0.0226,
                             'price': 23157.64,
                             'side': 'SELL',
                             'status': 'FILLED',
                             'ticker_id': 1,
                             'transacttime': datetime.datetime(2023, 1, 26, 8, 48, 31, 618000),
                             'type': 'LIMIT'})
        order = self.repository.get_order_by_id(binance_order['orderId'])
        self.assertEqual(target_order, order)
        self.repository.delete_order_by_id(binance_order['orderId'])


if __name__ == '__main__':
    unittest.main()
