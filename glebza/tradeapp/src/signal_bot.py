import json, os
import datetime
import requests
import logging

import service.signal_service as service
from concurrent.futures import ThreadPoolExecutor

import repository.signal_bot_repository as repository

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s: %(asctime)s %(name) at line %(lineno)  %(message)s', level=logging.INFO)
repo = repository.SignalBotRepository()

api_base_url = "https://fapi.binance.com/{}"
api_url_24h_price_changed = "fapi/v1/ticker/24hr"


response = requests.get(api_base_url.format(api_url_24h_price_changed))
tickers_data = {
    item['symbol']: {"24h_price_change": float(item['priceChangePercent']), "dt": datetime.datetime.now()} for
    item in
    response.json() if
    "USDC" not in item['symbol']}
hist_tickers_signal_data = repo.get_signals_count_for_today()
if len(hist_tickers_signal_data) > 0:
    for ticker in tickers_data:
        if ticker in hist_tickers_signal_data:
            tickers_data[ticker]["signal_count"] = hist_tickers_signal_data[ticker]

logger.info("ticker count {}".format(len(tickers_data)))

with ThreadPoolExecutor(max_workers=6) as executor:
    results = list(signal for signal in executor.map(service.check_for_signal, tickers_data.keys(), tickers_data.values()) if signal is not None)
    repo.save_signals_data(results)
