from glebza.tradeapp.src.repository.history_repository import HistoryRepository
import glebza.tradeapp.legacy.service.market_service as market_service
from datetime import datetime, timedelta
from binance import Client
import os


def prepare_data():
    repository = HistoryRepository()
    API_KEY = os.environ['API_KEY']
    API_SECRET = os.environ['API_SECRET']
    client = Client(API_KEY, API_SECRET)
    start_date = datetime(2024, 1, 1, 0, 0, 0)
    end_date = datetime(2024, 3, 31, 23, 59, 59)
    symbol = 'BTCUSDT'
    timeframe = '1m'
    klines = market_service.get_klines(client, symbol, timeframe, "01.01.2024 00:00:00", "31.01.2024 23:59:59")
    status = repository.save_klines_data(klines, timeframe)
    print(status)


prepare_data()
