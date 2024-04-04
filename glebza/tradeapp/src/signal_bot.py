import json, os
import requests
import logging
import adapters.telegram_adapter as adapter
from concurrent.futures import ThreadPoolExecutor

import repository.signal_bot_repository as repository

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', filename="signal_bot.log", level=logging.INFO)

repo = repository.SignalBotRepository()

resulting_message = """1h - {} - OI {} на {}%. 
Изменение cvd (1h) {}%
Изменение цены (24ч): {}% """

api_base_url = "https://fapi.binance.com/{}"
api_url_oi = "fapi/v1/openInterest?symbol={}"
api_url_oi_stat = "futures/data/openInterestHist?symbol={}&period=1h&limit=2"
api_long_short_ratio = "futures/data/takerlongshortRatio?symbol={}&period=1h&limit=2"
api_url_volumes = "fapi/v1/openInterest?symbol={}"
api_url_24h_price_changed = "fapi/v1/ticker/24hr?"


def check_for_signal(ticker_data):
    price_change = ticker_data["price_change"]
    symbol = ticker_data["symbol"]
    repeat_count = ticker_data["signal_count"]
    try:
        long_short_ratio_response = requests.get(api_base_url.format(api_long_short_ratio.format(symbol))).json()
        long_short_ratio_last_5m = long_short_ratio_response[0]
        long_short_ratio_current = long_short_ratio_response[1]
        cvd_before = float(long_short_ratio_last_5m['buyVol']) - float(long_short_ratio_last_5m['sellVol'])
        cvd_current = float(long_short_ratio_current['buyVol']) - float(long_short_ratio_current['sellVol'])
        cvd_percent_changed = round(cvd_current / cvd_before, 2) * 100
        interests = requests.get(api_base_url.format(api_url_oi_stat.format(symbol))).json()
        open_interests = [float(item["sumOpenInterest"]) for item in interests]
        # возвращаемые значения в обратном порядке: последнее значение - за текущую дату
        current_oi = float(requests.get(api_base_url.format(api_url_oi.format(symbol))).json()['openInterest'])
        oi_percent_changed = round((current_oi - open_interests[0]) / open_interests[0], 3) * 100
        logger.info("current_oi {} / open_interests[0] {} = {}".format(current_oi, open_interests[0],
                                                                       current_oi / open_interests[0]))

        if oi_percent_changed >= 1.5 and cvd_percent_changed > 10:
            send_to_telegram(round(oi_percent_changed, 3), "вырос", price_change, symbol, cvd_percent_changed,
                             repeat_count)
        else:
            logger.info("symbol: {}, oi_percent_changed: {}, cvd_changed: {}, price_change: {}, ".format(symbol,
                                                                                                         oi_percent_changed,
                                                                                                         cvd_percent_changed,
                                                                                                         price_change))
    except Exception:
        logger.error("symbol {} is invalid".format(symbol))


def send_to_telegram(oi_percent_changed, direction, price_change, symbol, cvd_changed, repeat_count):
    msg = resulting_message.format(symbol, direction, abs(oi_percent_changed), cvd_changed, price_change).join(
        repeat_count)
    logging.info(msg)
    adapter.send_message(msg)
    return symbol


# получить изменения цен +
# получить сигналы за сегодня +
# собрать json с данными для executors
# id, symbol, priceChangePercent, signal count
response = requests.get(api_base_url.format(api_url_24h_price_changed))
tickers_data = {item['symbol']: float(item['priceChangePercent']) for item in response.json() if
                "USDC" not in item['symbol']}
hist_tickers_signal_data = repo.get_signals_count_for_today()
if len(hist_tickers_signal_data) > 0:
    for symbol, value in tickers_data:
        tickers_data[symbol] = {"priceChangePercent": tickers_data[symbol],
                                "signal_count": hist_tickers_signal_data[symbol]["signal_count"]}

logger.info("ticker count {}".format(len(tickers_data)))

with ThreadPoolExecutor(max_workers=6) as executor:
    results = list(executor.map(check_for_signal, tickers_data))
