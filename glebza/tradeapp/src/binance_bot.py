from datetime import datetime, timedelta
import json, os
import websocket
from binance import Client
from binance.enums import *
import service.order_service as service
import strategies.boll_macd_rsi as strategy
import service.market_service as market_service
import logging
import time
import sys
from decimal import *

CLOSE_INTERVAL = 'T'

IS_CANDLE_CLOSE = 'x'

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)

API_KEY = os.environ['API_KEY']
API_SECRET = os.environ['API_SECRET']
SYMBOL = 'BTCUSDT'
ACTION_BUY = 'BUY'
ACTION_SELL = 'SELL'

START_CASH = 700

client = Client(API_KEY, API_SECRET)

sell_order = None
buy_order = service.get_open_deal_order(SYMBOL)

if buy_order is not None:
    logging.info('There is an open deal: ')
    logging.info(buy_order)
else:
    logging.info('There is no open deal: ')

warm_data = None

if len(sys.argv) > 1:
    warm_data = market_service.get_transformed_klines(client, SYMBOL, sys.argv[0], sys.argv[1])
else:
    warm_data = market_service.get_transformed_klines(client, SYMBOL)

close_prices = warm_data[0]
high_prices = warm_data[2]
low_prices = warm_data[3]
strategy.prepare(warm_data)

# start is required to initialise its internal loop
# TODO   реализовать teardown
def handle_socket_message(ws, msg):
    global buy_order
    global sell_order
    global SYMBOL

    st = time.time()
    candle = json.loads(msg)['k']
    closed_price =float (candle['c'])
    high_price = float(candle['h'])
    low_price = float(candle['l'])

    if buy_order and buy_order['status'] != ORDER_STATUS_FILLED:
        qty = round(float(START_CASH) / closed_price, 5)
        buy_order = service.open_deal(client, SYMBOL, closed_price, qty)
        et = time.time()
        logging.info('Do buy: Execution time: {} {}'.format(et - st, 'seconds'))

    if sell_order and sell_order['status'] != ORDER_STATUS_FILLED:
        sell_order = service.close_deal(client, SYMBOL, float(closed_price), buy_order)
        et = time.time()
        logging.info('Do sell: Execution time:{} {}'.format(et - st, 'seconds'))

    if sell_order and sell_order['status'] == ORDER_STATUS_FILLED:
        logging.info(
            'the deal is closed: open order {}, close order {}'.format(buy_order['orderId'], sell_order['orderId']))
        buy_order = None
        sell_order = None

    if candle[IS_CANDLE_CLOSE]:
        close_prices.append(float(closed_price))
        high_prices.append(high_price)
        low_prices.append(low_price)
        prices = closed_price,high_prices,low_prices
        logging.info("----")
        track = strategy.process(prices, candle[CLOSE_INTERVAL], buy_order)

        if track['action'] == ACTION_SELL:
            logging.info('sell!')
            sell_order = service.close_deal(client, SYMBOL, closed_price, buy_order)
            buy_order = None

        if track['action'] == ACTION_BUY:
            qty = round(START_CASH / closed_price, 5)
            buy_order = service.open_deal(client, SYMBOL, closed_price, qty)
            et = time.time()
            logging.info('Normal buy: Execution time:{} {}'.format(et - st, 'seconds'))


def on_error(ws, error):
    logging.info(error)


def on_close(ws, txt, error):
    logging.info("### closed ### {}".format(ws))


logging.info('start listening {}'.format(SYMBOL))
SOCKET = 'wss://stream.binance.com:443/ws/btcusdt@kline_1m'
websocket.enableTrace(False)
ws = websocket.WebSocketApp(SOCKET,
                            on_message=handle_socket_message,
                            on_error=on_error,
                            on_close=on_close)
ws.run_forever()
