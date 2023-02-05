import unittest
from unittest.mock import MagicMock
from repository.binance_bot_repository import BinanceBotRepository
import datetime


class OrderRepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.repository = BinanceBotRepository()
        self.order_id = 17811919231

    def test_save_order(self):
        binance_order = dict(
            {'symbol': 'BTCUSDT', 'orderId': self.order_id, 'orderListId': -1,
             'clientOrderId': 'ios_80b2f1a144b049308c7702da46ae2358', 'price': '23157.64000000',
             'origQty': '0.02260000', 'executedQty': '0.02260000', 'cummulativeQuoteQty': '523.36266400',
             'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'SELL', 'stopPrice': '0.00000000',
             'icebergQty': '0.00000000', 'time': 1674712111618, 'updateTime': 1674712120546, 'isWorking': True,
             'workingTime': 1674712111618, 'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'NONE'})
        self.repository.save_order(binance_order)
        target_order = dict({'clientorderid': 'ios_80b2f1a144b049308c7702da46ae2358',
                             'executedqty': 0.0226,
                             'id': self.order_id,
                             'orderlistid': -1,
                             'origqty': 0.0226,
                             'price': 23157.64,
                             'side': 'SELL',
                             'status': 'FILLED',
                             'ticker_id': 1,
                             'transacttime': datetime.datetime(2023, 1, 26, 8, 48, 31, 618000),
                             'type': 'LIMIT',
                             'symbol': 'BTCUSDT',
                             'time': 1674685872599})
        order = self.repository.get_order_by_id(binance_order['orderId'])
        self.assertEqual(target_order, order)

    def tearDown(self):
        self.repository.delete_order_by_id(self.order_id)


class DealRepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.repository = BinanceBotRepository()
        self.buy_order = dict(
            {'symbol': 'BTCUSDT', 'orderId': 17799280507, 'orderListId': -1, 'clientOrderId': 'bU2iE4DQGRsUP7euHmw5QE',
             'price': '23451.65000000', 'origQty': '0.02260000', 'executedQty': '0.02260000',
             'cummulativeQuoteQty': '530.00616000', 'status': 'FILLED', 'timeInForce': 'FOK', 'type': 'LIMIT',
             'side': 'BUY', 'stopPrice': '0.00000000', 'icebergQty': '0.00000000', 'time': 1674685872599,
             'updateTime': 1674685872599, 'isWorking': True, 'workingTime': 1674685872599,
             'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'NONE'})
        self.sell_order = dict({'symbol': 'BTCUSDT', 'orderId': 17811919231, 'orderListId': -1,
                                'clientOrderId': 'ios_80b2f1a144b049308c7702da46ae2358', 'price': '23157.64000000',
                                'origQty': '0.02260000', 'executedQty': '0.02260000',
                                'cummulativeQuoteQty': '523.36266400', 'status': 'FILLED', 'timeInForce': 'GTC',
                                'type': 'LIMIT', 'side': 'SELL', 'stopPrice': '0.00000000', 'icebergQty': '0.00000000',
                                'time': 1674712111618, 'updateTime': 1674712120546, 'isWorking': True,
                                'workingTime': 1674712111618, 'origQuoteOrderQty': '0.00000000',
                                'selfTradePreventionMode': 'NONE'})

        self.repository.save_order(self.buy_order)

    def test_save_deal(self):
        self.repository.save_deal(self.buy_order)
        target_deal = dict({'buy_order_id': self.buy_order['orderId'],
                            'end_date': None,
                            'sell_order_id': None,
                            'start_date': datetime.datetime(2023, 1, 26, 1, 31, 12, 599000),
                            'ticker_id': 1})
        deal = self.repository.get_deal_by_id(self.buy_order['orderId'])
        self.assertEqual(target_deal, deal)

    def test_update_deal(self):
        self.repository.save_deal(self.buy_order)
        self.repository.update_deal(self.buy_order, self.sell_order)
        deal = self.repository.get_deal_by_id(self.buy_order['orderId'])
        target_deal = ({'buy_order_id': 17799280507,
                        'end_date': None,
                        'sell_order_id': None,
                        'start_date': datetime.datetime(2023, 1, 26, 1, 31, 12, 599000),
                        'ticker_id': 1})
        self.assertEqual(target_deal, deal)

    def test_get_open_deal_order(self):
        self.repository.save_deal(self.buy_order)
        order = self.repository.get_open_deal_order('BTCUSDT')
        target_order = dict({'clientorderid': 'bU2iE4DQGRsUP7euHmw5QE',
                             'executedQty': 0.0226,
                             'orderId': 17799280507,
                             'orderlistid': -1,
                             'origqty': 0.0226,
                             'price': 23451.65,
                             'side': 'BUY',
                             'status': 'FILLED',
                             'ticker_id': 1,
                             'transacttime': datetime.datetime(2023, 1, 26, 1, 31, 12, 599000),
                             'type': 'LIMIT',
                             'symbol': 'BTCUSDT',
                             'time': 1674685872599,})
        self.assertEqual(target_order, order)

    def tearDown(self):
        self.repository.delete_deal_by_id(self.buy_order['orderId'])
        self.repository.delete_order_by_id(self.buy_order['orderId'])


if __name__ == '__main__':
    unittest.main()
