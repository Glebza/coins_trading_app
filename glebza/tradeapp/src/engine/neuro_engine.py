import numpy
import numpy as np
from talib import MA_Type
from strategies.neuronetwork import NeuroNetwork
import service.order_service as service
import service.market_service as m_service
import logging
import csv
from datetime import datetime, timedelta
from binance import Client
import talib

from glebza.tradeapp.tests.backtest.repository.backtest_repository import BacktestRepository

portfolio_sum = 700
qty = 0

RSI_PERIOD = 15

MINUTES_IN_THE_DAY = 125

SYMBOL = 'BTCUSDT'

FILENAME = '/Users/ruasyg4/PycharmProjects/CoinsTradeApp/glebza/tradeapp/tests/backtest/resources/backtest_data.csv'

k_interval_idx = 0
open_idx = 1
high_idx = 2
low_idx = 3
close_idx = 4
volume_idx = 5

volumes = []
closes = []
high_prices = []
low_prices = []

market_caps_steps = []
overall_volume = 0
overall_market_cap_steps = 0

# start_date = datetime(2022, 11, 30, 0, 0, 0).strftime("%m/%d/%Y, %H:%M:%S")
# end_date = datetime(2022, 11, 30, 1, 20, 59)
start_date = '01.12.2022 00:00:00'
end_date = '03.12.2022 23:59:00'

client = Client()
repository = BacktestRepository()
neuro_network = NeuroNetwork()

f = open(FILENAME, 'w')
writer = csv.writer(f)
writer.writerow(
    ['k_interval', 'close_price', 'volume', 'market_cap', 'atr',
     'rsi_15', 'rsi_9', 'macd', 'macd_sygnal', 'macd_diff', 'boll_low', 'boll_middle', 'boll_high', 'is_grown'])

klines = client.get_historical_klines(SYMBOL, client.KLINE_INTERVAL_1MINUTE, start_str=start_date, end_str=end_date)
print('got data')

k_line_count = 0

model_k_intervals = []
model_close_prices = []
model_volumes = []
model_market_caps = []
model_atrs = []
model_rsi_15s = []
model_rsi_9s = []
model_macds = []
model_macd_sygnals = []
model_macd_diffs = []
model_boll_lows = []
model_boll_middleses = []
model_boll_highs = []
model_k_grown = []

time_to_learn = False
is_learning_set = True

total_prediction_count = 0
correct_predictions = 0

cryptos = ({'k_intervals': model_k_intervals, 'close_prices': model_close_prices, 'volumes': model_volumes,
            'market_caps': model_market_caps, 'atrs': model_atrs, 'rsi_15': model_rsi_15s, 'rsi_9': model_rsi_9s,
            'macd': model_macds, 'macd_sygnal': model_macd_sygnals, 'macd_diff': model_macd_diffs,
            'boll_low': model_boll_lows, 'boll_middle': model_boll_middleses, 'boll_high': model_boll_highs,
            'k_grown': model_k_grown})

for kline in klines:
    k_line_count = k_line_count + 1
    if len(klines) == k_line_count:
        break
    next_k_close = float(klines[k_line_count][close_idx])
    close_price = float(kline[close_idx])
    volume = float(kline[volume_idx])

    high_price = float(kline[high_idx])
    low_price = float(kline[low_idx])
    typical_price = float((close_price + high_price + low_price) / 3)
    current_market_cap_step = typical_price * volume

    overall_volume = overall_volume + volume
    overall_market_cap_steps = overall_market_cap_steps + current_market_cap_step

    volumes.append(volume)
    closes.append(close_price)
    high_prices.append(high_price)
    low_prices.append(low_price)
    market_caps_steps.append(current_market_cap_step)

    if k_line_count > MINUTES_IN_THE_DAY:
        volumes.pop(0)
        closes.pop(0)
        high_prices.pop(0)
        low_prices.pop(0)
        np_closes = numpy.array(closes)
        np_high_prices = numpy.array(high_prices)
        np_low_prices = numpy.array(low_prices)
        k_interval = kline[k_interval_idx] * 1000
        market_cap = overall_market_cap_steps - market_caps_steps.pop(0)
        rsi_15 = talib.RSI(np_closes, RSI_PERIOD)
        rsi_9 = talib.RSI(np_closes, 9)
        macd, macd_sygnal, macd_diff = talib.MACD(np_closes, fastperiod=15, slowperiod=26, signalperiod=9)
        boll_high, boll_middle, boll_low = talib.BBANDS(np_closes, timeperiod=21, matype=MA_Type.T3)
        atr = talib.ATR(np_high_prices, np_low_prices, np_closes, timeperiod=RSI_PERIOD)
        is_grown = 1 if next_k_close > close_price else 0
        if is_learning_set:
            row = (
                k_interval, close_price, volume, market_cap, atr[-1], rsi_15[-1], rsi_9[-1], macd[-1], macd_sygnal[-1],
                macd_diff[-1], boll_low[-1], boll_middle[-1], boll_high[-1], is_grown
            )
            writer.writerow(row)

            model_k_intervals.append(k_interval)
            model_close_prices.append(close_price)
            model_volumes.append(volume)
            model_market_caps.append(market_cap)
            model_atrs.append(atr[-1])
            model_rsi_15s.append(rsi_15[-1])
            model_rsi_9s.append(rsi_9[-1])
            model_macds.append(macd[-1])
            model_macd_sygnals.append(macd_sygnal[-1])
            model_macd_diffs.append(macd_diff[-1])
            model_boll_lows.append(boll_low[-1])
            model_boll_middleses.append(boll_middle[-1])
            model_boll_highs.append(boll_high[-1])
            model_k_grown.append(is_grown)
        else:

            if qty != 0:
                portfolio_sum = qty * close_price
                qty = 0
            total_prediction_count = total_prediction_count + 1
            pred_set = np.array(
                [[k_interval], [close_price], [volume], [market_cap], [atr[-1]], [rsi_15[-1]], [rsi_9[-1]], [macd[-1]],
                 [macd_sygnal[-1]],
                 [macd_diff[-1]], [boll_low[-1]], [boll_middle[-1]], [boll_high[-1]]]).T
            print(pred_set)
            prediction = neuro_network.predict(pred_set)[0]
            if prediction == 1:
                qty = float(portfolio_sum / close_price)

            correct_predictions = correct_predictions + (1 if is_grown == prediction else 0)

        # repository.save_klines_with_metricks()
    if k_line_count == 825:
        print('start the challenge')
        f.close()
        neuro_network.learn(cryptos)
        is_learning_set = False

print('correct predictions = {}. total number of predictions = {}. rate= {}'.format(correct_predictions,
                                                                                    total_prediction_count,
                                                                                    correct_predictions / total_prediction_count))
print('sum = {}'.format(portfolio_sum))
