import unittest
from unittest.mock import MagicMock
import datetime

from binance import Client

import service.order_service as service
from repository.binance_bot_repository import BinanceBotRepository

SYMBOl = 'BTCUSDT'

class OrderServiceTestCase(unittest.TestCase):

    def setUp(self):
        self.repository = BinanceBotRepository()

        self.buy_order = dict({'symbol': 'BTCUSDT', 'orderId': 17799280507, 'orderListId': -1, 'clientOrderId': 'bU2iE4DQGRsUP7euHmw5QE',
             'price': '23451.65000000', 'origQty': '0.02260000', 'executedQty': '0.02260000',
             'cummulativeQuoteQty': '530.00616000', 'status': 'FILLED', 'timeInForce': 'FOK', 'type': 'LIMIT',
             'side': 'BUY', 'stopPrice': '0.00000000', 'icebergQty': '0.00000000', 'time': 1674685872599,
             'updateTime': 1674685872599, 'isWorking': True, 'workingTime': 1674685872599,
             'origQuoteOrderQty': '0.00000000', 'selfTradePreventionMode': 'NONE'})

    def test_open_deal(self):
        client = Client()
        client.create_order = MagicMock(return_value=self.buy_order)
        client.get_order = MagicMock(return_value=self.buy_order)
        order = service.open_deal(client, SYMBOl, self.buy_order['price'], self.buy_order['origQty'])
        target_deal = dict({'buy_order_id': self.buy_order['orderId'],
                            'end_date': None,
                            'sell_order_id': None,
                            'start_date': datetime.datetime(2023, 1, 26, 1, 31, 12, 599000),
                            'ticker_id': 1})
        deal = self.repository.get_deal_by_id(self.buy_order['orderId'])

        client.get_order.assert_called_with(symbol=SYMBOl, orderId=self.buy_order['orderId'])
        self.assertEqual(self.buy_order, order)
        self.assertEqual(target_deal, deal)

    def tearDown(self):
        self.repository.delete_deal_by_id(self.buy_order['orderId'])
        self.repository.delete_order_by_id(self.buy_order['orderId'])


if __name__ == '__main__':
    unittest.main()
