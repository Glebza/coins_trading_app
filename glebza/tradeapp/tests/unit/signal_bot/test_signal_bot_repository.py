from unittest.mock import MagicMock
from unittest.mock import Mock
import unittest, os, psycopg2, logging
from datetime import timedelta, datetime
from repository.signal_bot_repository import SignalBotRepository

OPEN_INTEREST = 99


class SignalRepositoryTestCase(unittest.TestCase):
#получаем на вход тицкеры
#достаем из базы все записи по тицкеру за день (то есть на вход репозитория получаем тицкер)
#обрабатываем событие
#если отправили сигнал то сохраняем в бд. на вход приходит тицкер

    def setUp(self):
        self.repository = SignalBotRepository()
        test_records = [(datetime.now(),"BTCUSDT", OPEN_INTEREST, 99.04, -0.99, ),
                        (datetime.today() - timedelta(days=1),"BTCUSDT", 30, 15.04, -0.5, )]
        self.test_rows_ids = self.repository.save_signals_data(test_records)

    def test_get_signals_count_for_today(self):
        rows = self.repository.get_signals_count_for_today()
        self.assertEqual(1, len(rows))
        self.assertEqual(True, "BTCUSDT" in rows)

    def tearDown(self):
        self.repository.delete_signals_by_(self.test_rows_ids)
        print("the end!")
