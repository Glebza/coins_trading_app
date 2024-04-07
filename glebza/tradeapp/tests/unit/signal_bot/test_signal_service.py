import unittest, requests, json
from unittest.mock import MagicMock
from unittest.mock import Mock

from datetime import timedelta,datetime

import adapters.telegram_adapter
import service.signal_service as service
from repository.signal_bot_repository import SignalBotRepository

SYMBOl = 'BTCUSDT'


class TestResponse:

    def __init__(self, msg):
        self.msg = msg

    def json(self):
        return self.msg


class SignalServiceTestCase(unittest.TestCase):

    def setUp(self):
        self.repository = SignalBotRepository()

        self.input_data_without_history = dict({"24h_price_change": -0.620, "dt":datetime.now()})
        self.input_data_with_history = dict(
            {"24h_price_change": -0.620, "dt": datetime.now(), "repeat_count": 3})

    def mock_requests_response(self, arg):
        msg = ""
        if "https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=1h&limit=2" == arg:
            msg = TestResponse(
                [{"buySellRatio": "0.7550", "sellVol": "2900.1870", "buyVol": "2000.2990", "timestamp": 1712300400000},
                 {"buySellRatio": "1.1186", "sellVol": "7000.4070", "buyVol": "9000.7200", "timestamp": 1712304000000}])
        if "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&limit=2" == arg:
            msg = TestResponse([
                {
                    "symbol": "BTCUSDT",
                    "sumOpenInterest": "60000.33400000",
                    "sumOpenInterestValue": "5164660507.12673900",
                    "timestamp": datetime.today() - timedelta(hours=0, minutes=50)
                },
                {
                    "symbol": "BTCUSDT",
                    "sumOpenInterest": "80000.06000000",
                    "sumOpenInterestValue": "5164222086.44676600",
                    "timestamp": datetime.now()
                }
            ])
        if "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT" == arg:
            msg = TestResponse({"symbol":"BTCUSDT","openInterest":"90086.216","time":1712303620184})

        return msg

    def test_check_for_signal_arose(self):
        service.send_to_telegram = MagicMock()
        requests.get = Mock(side_effect=self.mock_requests_response)

        result_with_history = service.check_for_signal("BTCUSDT", self.input_data_with_history)
        result_without = service.check_for_signal("BTCUSDT", self.input_data_without_history)

        self.assertEqual(('BTCUSDT',50.1,322.0,-0.62,4), result_with_history[1:])
        self.assertEqual(('BTCUSDT',50.1,322.0,-0.62,1), result_without[1:])

    def tearDown(self):
        print("the end!")


if __name__ == '__main__':
    unittest.main()
