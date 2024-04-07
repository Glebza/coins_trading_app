from unittest.mock import MagicMock
from unittest.mock import Mock
import unittest, os, psycopg2, logging
from datetime import timedelta, datetime
from repository.signal_bot_repository import SignalBotRepository


class SignalRepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.repository = SignalBotRepository()
        test_records = [(1, 99, 99.04, -0.99, datetime.now()),
                        (1, 30, 15.04, -0.5, datetime.today() - timedelta(days=1))]
        self.repository.save_signals_data(test_records)

    def test_get_signals_count_for_today(self):
        rows = self.repository.get_signals_count_for_today()
        self.assertEqual(1, len(rows))
        self.assertEqual(99, rows[0][1])

    def tearDown(self):
        print("the end!")
