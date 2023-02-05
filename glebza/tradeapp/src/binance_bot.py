from datetime import datetime, timedelta
import json, numpy, talib, os
import websocket
from binance import Client, ThreadedWebsocketManager, ThreadedDepthCacheManager
from binance.enums import *
from repository.binance_bot_repository import BinanceBotRepository
from talib import MA_Type
from binance.exceptions import BinanceAPIException
import logging
import time

logging.basicConfig(format='%(levelname)s: %(asctime)s %(message)s', level=logging.DEBUG)
PROFIT_RATE = 8
API_KEY = os.environ['API_KEY']
API_SECRET = os.environ['API_SECRET']
SYMBOL = 'BTCUSDT'
RSI_PERIOD = 15
RSI_OVERSOLD = 52
RSI_OVERBOUGHT = 70
START_CASH = 700

client = Client(API_KEY, API_SECRET)
repository = BinanceBotRepository()

do_buy = False
do_sell = False

sell_order = None
buy_order = repository.get_open_deal_order(SYMBOL)
if buy_order is not None:
    logging.info('There is an open deal: ')
    logging.info(buy_order)
else:
    logging.info('There is no open deal: ')


def warm_up(client, ticker):
    logging.info(ticker)
    volumes = []
    closes = []
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=1)).strftime("%d/%m/%Y, %H:%M:%S")
    klines = client.get_historical_klines(SYMBOL, Client.KLINE_INTERVAL_1MINUTE, "1 day ago UTC")
    start_interval = 0
    open_p = 1
    high = 2
    low = 3
    close = 4
    volume = 5
    for kline in klines:
        volumes.append(float(kline[volume]))
        closes.append(float(kline[close]))
    return closes, volumes


warm_data = warm_up(client, SYMBOL)
volumes = warm_data[1]
close_prices = warm_data[0]


# start is required to initialise its internal loop
def handle_socket_message(ws, msg):
    global buy_order
    global sell_order
    global SYMBOL
    global repository
    global do_buy

    st = time.time()
    candle = json.loads(msg)['k']
    is_candle_closed = candle['x']
    closed_price = float(candle['c'])
    volume = candle['v']

    if do_buy:
        buy_order = open_deal(SYMBOL, repository, float(closed_price))
        et = time.time()
        logging.info('Do buy: Execution time: {} {}'.format(et - st,'seconds'))

        return
    if do_sell:
        sell_order = close_deal(SYMBOL, repository, float(closed_price), buy_order)
        et = time.time()
        logging.info('Do sell: Execution time:{} {}'.format(et - st,'seconds'))
        return

    upper, middle, lower = talib.BBANDS(numpy.array(close_prices), timeperiod=21, matype=MA_Type.T3)

    buy_order = update_order_status(buy_order, SYMBOL, repository)
    sell_order = update_order_status(sell_order, SYMBOL, repository)

    if sell_order and sell_order['status'] == ORDER_STATUS_FILLED:
        logging.info(
            'the deal is closed: open order {}, close order {}'.format(buy_order['orderId'], sell_order['orderId']))
        buy_order = None
        sell_order = None
    else:
        # try to catch the price's peaks
        if buy_order and float(closed_price) > float(buy_order['price']) and (
                float(closed_price) - float(upper[-1]) > 2 * PROFIT_RATE):
            logging.info('peak detected! Diff {}'.format(closed_price - float(upper[-1])))
            logging.info(
                "price {}, upper {}, middle {}, lower {}".format(buy_order['price'], upper[-1], middle[-1], lower[-1]))
            sell_order = close_deal(SYMBOL, repository, closed_price, buy_order)

    # if not buy_order and (float(lower[-1]) - float(closed_price) > 2 * PROFIT_RATE):
    #     logging.info('pit detected! Diff {}'.format(lower[-1] - float(closed_price)))
    #     logging.info("price {}, upper {}, middle {}, lower {}".format(closed_price, upper[-1], middle[-1], lower[-1]))
    #     buy_order = open_deal(SYMBOL, repository, closed_price)

    if is_candle_closed:
        close_prices.append(float(closed_price))
        volumes.append(float(volume))
        np_closes = numpy.array(close_prices)
        np_volumes = numpy.array(volumes)
        rsi = talib.RSI(np_closes, RSI_PERIOD)
        obv = talib.OBV(np_closes, np_volumes)
        ma = talib.MA(np_closes, RSI_PERIOD)
        macd, signal, macd_diff = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)
        logging.info("----")

        if buy_order:
            if buy_order['status'] == ORDER_STATUS_FILLED and not sell_order:
                diff = float(closed_price) - float(buy_order['price'])
                logging.info("diff = {}".format(diff))
                if diff >= PROFIT_RATE:
                    logging.info('sell!')
                    sell_order = close_deal(SYMBOL, repository, closed_price, buy_order)
        else:
            if rsi[-2] < RSI_OVERSOLD \
                    and macd[-1] > signal[-1] and macd[-2] <= signal[-2] and macd[-1] < 0:
                buy_order = open_deal(SYMBOL, repository, closed_price)
                et = time.time()
                logging.info('Normal buy: Execution time:{} {}'.format(et - st, 'seconds'))


def open_deal(symbol, repository, closed_price):
    global do_buy
    qty = round(START_CASH / closed_price, 5)
    side = Client.SIDE_BUY
    order = execute_order(client, closed_price, float(qty), repository, side, symbol)
    if order['status'] != ORDER_STATUS_FILLED:
        do_buy = True
        logging.info('Buy failed!')
    else:
        logging.info('Buy successful!')
        do_buy = False
        repository.save_deal(order)
    return order


def close_deal(symbol, repository, closed_price, order):
    global do_sell
    side = Client.SIDE_SELL
    sell_order = execute_order(client, closed_price, order['executedQty'], repository, side, symbol)
    if sell_order['status'] != ORDER_STATUS_FILLED:
        do_sell = True
        logging.info('Sell failed!')
    else:
        logging.info('Sell successful!')
        do_sell = False
        repository.update_deal(order, sell_order)
    return sell_order


def execute_order(client, closed_price, qty, repository, side, symbol):
    price = closed_price
    order = None
    order_id = place_order(client,
                           symbol,
                           side,
                           Client.ORDER_TYPE_LIMIT,
                           price,
                           qty)['orderId']
    order = client.get_order(symbol=symbol, orderId=order_id)
    if order['status'] == ORDER_STATUS_FILLED:
        repository.save_order(order=order)
    return order


def place_order(client, symbol, side, type, price, quantity):
    order = None
    try:
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=type,
            timeInForce=TIME_IN_FORCE_FOK,
            quantity=quantity,
            price=price
        )
        logging.info(order)
    except Exception as e:
        logging.error(e)
    return order


def cancel_order(client, symbol, order):
    logging.info('try to cancel order {}'.format(order['orderId']))
    try:
        order = client.cancel_order(symbol=symbol, orderId=order['orderId'])
        logging.info('order cancelled ', order)
    except Exception as e:
        logging.error(e)
    return order


def update_order_status(order, symbol, repository):
    if order:
        if order['status'] != ORDER_STATUS_FILLED:
            order = client.get_order(symbol=symbol, orderId=order['orderId'])
            status = order['status']
            repository.update_order_status(order_id=order['orderId'], status=status,
                                           executedqty=order['executedQty'])

    return order


def on_error(ws, error):
    logging.info(error)


def on_close(ws, txt, error):
    logging.info("### closed ### {}".format(ws))


logging.info('start listening {}'.format(SYMBOL))

# order = place_order(client, symbol, Client.SIDE_BUY,float(36300), 0.001684)
# order = {'symbol': 'BTCUSDT', 'orderId': 6183087675, 'orderListId': -1, 'clientOrderId': 'hzf8ut8BgIrCUh7Ey4kdgC', 'transactTime': 1622133593112, 'price': '38900.00000000', 'origQty': '0.00168400', 'executedQty': '0.00168400', 'cummulativeQuoteQty': '65.42289480', 'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'BUY', 'fills': [{'price': '38849.70000000', 'qty': '0.00168400', 'commission': '0.00000168', 'commissionAsset': 'BTC', 'tradeId': 875740731}]}

# twm = ThreadedWebsocketManager(api_key=API_KEY, api_secret=API_SECRET)
# twm.start()
# twm.start_kline_socket(callback=handle_socket_message, symbol=symbol, interval=KLINE_INTERVAL_1MINUTE)
# twm.join()
SOCKET = 'wss://stream.binance.com:443/ws/btcusdt@kline_1m'
websocket.enableTrace(False)
ws = websocket.WebSocketApp(SOCKET,
                            on_message=handle_socket_message,
                            on_error=on_error,
                            on_close=on_close)
ws.run_forever()
