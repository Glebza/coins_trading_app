import json, os
import requests
import adapters.telegram_adapter as adapter

resulting_message = """5m - {} - OI {} на {}%. 
Изменение cvd (5m) {}%
Изменение цены (24ч): {}% """

api_base_url = "https://fapi.binance.com/{}"
api_url_exchange_info = "https://fapi.binance.com/fapi/v1/exchangeInfo"
api_url_oi = "fapi/v1/openInterest?symbol={}"
api_url_oi_stat = "futures/data/openInterestHist?symbol={}&period=5m&limit=2"
api_long_short_ratio = "futures/data/takerlongshortRatio?symbol={}&period=5m&limit=2"
api_url_volumes = "fapi/v1/openInterest?symbol={}"
api_url_24h_price_changed = "fapi/v1/ticker/24hr?"


def check_for_signal(symbol, price_change):
    try:
        long_short_ratio_response = requests.get(api_base_url.format(api_long_short_ratio.format(symbol))).json()
        long_short_ratio_last_5m = long_short_ratio_response[0]
        long_short_ratio_current = long_short_ratio_response[1]
        cvd_before = float(long_short_ratio_last_5m['buyVol']) - float(long_short_ratio_last_5m['sellVol'])
        cvd_current = float(long_short_ratio_current['buyVol']) - float(long_short_ratio_current['sellVol'])
        cvd_percent_changed = round(cvd_current / cvd_before, 2) * 100
        interests = requests.get(api_base_url.format(api_url_oi_stat.format(symbol))).json()
        open_interests = [float(item["sumOpenInterest"]) for item in interests]
        avg_oi = sum(open_interests) / len(open_interests)
        # возвращаемые значения в обратном порядке: последнее значение - за текущую дату
        current_oi = float(requests.get(api_base_url.format(api_url_oi.format(symbol))).json()['openInterest'])
        oi_percent_changed = round((current_oi - open_interests[0]) / open_interests[0], 3) * 100
        print("current_oi {} / open_interests[0] {} = {}".format(current_oi, open_interests[0],
                                                                 current_oi / open_interests[0]))

        if oi_percent_changed >= 1 and cvd_percent_changed > 10:
            send_to_telegram(oi_percent_changed, "вырос", price_change, symbol, cvd_percent_changed)
        else:
            print("symbol: {}, oi_percent_changed: {}, cvd_changed: {}, price_change: {}, ".format(symbol,
                                                                                                   oi_percent_changed,
                                                                                                   cvd_percent_changed,
                                                                                                   price_change))

        # if oi_percent_changed <= -5.0:
        #  send_to_telegram(oi_percent_changed, "упал", price_change, symbol)
    except Exception:
        print("symbol {} is invalid".format(symbol))


def send_to_telegram(oi_percent_changed, direction, price_change, symbol, cvd_changed):
    msg = resulting_message.format(symbol, direction, abs(oi_percent_changed), cvd_changed, price_change)
    print(msg)
    adapter.send_message(msg)


response = requests.get(api_base_url.format(api_url_24h_price_changed))
data = {item['symbol']: float(item['priceChangePercent']) for item in response.json()}

for symbol, price_change in data.items():
    check_for_signal(symbol, price_change)
