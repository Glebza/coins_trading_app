import requests,logging
import adapters.telegram_adapter as adapter


api_base_url = "https://fapi.binance.com/{}"
api_long_short_ratio = "futures/data/takerlongshortRatio?symbol={}&period=1h&limit=2"
api_url_oi = "fapi/v1/openInterest?symbol={}"
api_url_oi_stat = "futures/data/openInterestHist?symbol={}&period=1h&limit=2"
api_url_volumes = "fapi/v1/openInterest?symbol={}"
resulting_message = """1h - {} - OI {} на {}%. 
Изменение cvd (1h) {}%
Изменение цены (24ч): {}% 
Повторение: {}"""

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(levelname)s: %(asctime)s %(name)s at line %(lineno)s  %(message)s', level=logging.INFO)


def check_for_signal(symbol,ticker_data):
    price_change = round(ticker_data["24h_price_change"],2)

    signal = None
    try:
        long_short_ratio_response = requests.get(api_base_url.format(api_long_short_ratio.format(symbol))).json()
        long_short_ratio_last_interval = long_short_ratio_response[0]
        long_short_ratio_current = long_short_ratio_response[1]
        cvd_before = float(long_short_ratio_last_interval['buyVol']) - float(long_short_ratio_last_interval['sellVol'])
        cvd_current = float(long_short_ratio_current['buyVol']) - float(long_short_ratio_current['sellVol'])
        cvd_percent_changed = round((cvd_current - cvd_before) / abs(cvd_before), 2) * 100
        interests = requests.get(api_base_url.format(api_url_oi_stat.format(symbol))).json()
        open_interests = [float(item["sumOpenInterest"]) for item in interests]
        # возвращаемые значения в обратном порядке: последнее значение - за текущую дату
        current_oi = float(requests.get(api_base_url.format(api_url_oi.format(symbol))).json()['openInterest'])
        oi_percent_changed = round((current_oi - open_interests[0]) / open_interests[0], 3) * 100
        logger.debug("current_oi {} / open_interests[0] {} = {}".format(current_oi, open_interests[0],
                                                                       current_oi / open_interests[0]))
        if oi_percent_changed >= 1.5:
            repeat_count = int(ticker_data["repeat_count"]) + 1 if "repeat_count" in ticker_data else 1
            send_to_telegram(round(oi_percent_changed, 3), "вырос", price_change, symbol, cvd_percent_changed,
                             repeat_count)
            signal = ticker_data['dt'], symbol, oi_percent_changed, cvd_percent_changed, price_change, repeat_count
        else:
            logger.debug("symbol: {}, oi_percent_changed: {}, cvd_changed: {}, price_change: {}, ".format(symbol,
                                                                                                         oi_percent_changed,
                                                                                                         cvd_percent_changed,
                                                                                                         price_change,
                                                                                                         ))
    except Exception as inst:
        logger.exception(inst)
        logger.error("symbol {} is invalid".format(symbol))

    return signal


def send_to_telegram(oi_percent_changed, direction, price_change, symbol, cvd_changed, repeat_count):
    msg = resulting_message.format(symbol, direction, abs(oi_percent_changed), cvd_changed, price_change, repeat_count)
    logging.info(msg)
    adapter.send_message(msg)

