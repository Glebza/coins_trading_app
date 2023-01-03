from datetime import datetime, timedelta
import json, pprint, numpy, talib, os
import websocket
from binance import Client, ThreadedWebsocketManager, ThreadedDepthCacheManager
from binance import ThreadedWebsocketManager
from binance.enums import *
from repository.binance_bot_repository import BinanceBotRepository
from binance.exceptions import BinanceAPIException

API_KEY = os.environ['API_KEY']
API_SECRET = os.environ['API_SECRET']
client = Client(API_KEY, API_SECRET)
symbol = 'BTCUSDT'
RSI_PERIOD = 15
RSI_OVERSOLD = 45
RSI_OVERBOUGHT = 70
START_CASH = 400


def warm_up(client, ticker):
    print(ticker)
    volumes = []
    closes = []
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=1)).strftime("%d/%m/%Y, %H:%M:%S")
    klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1MINUTE, "1 day ago UTC")
    start_interval = 0
    open_p = 1
    high = 2
    low = 3
    close = 4
    volume = 5
    for kline in klines:
        volumes.append(float(kline[volume]))
        closes.append(float(kline[close]))
    return (closes, volumes)


warm_data = warm_up(client, symbol)
volumes = warm_data[1]
close_prices = warm_data[0]
print(close_prices)
repository = BinanceBotRepository()
order = repository.get_open_deal_order(symbol)

def place_order(client, symbol, side, price, quantity):
    order = None
    try:
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=Client.ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            quantity=quantity,
            price=price
        )
        print(order)
    except Exception as e:
        print(e)
    return order


# start is required to initialise its internal loop
def handle_socket_message(ws, msg):
    global order
    global symbol
    global repository

    candle = json.loads(msg)['k']
    is_candle_closed = candle['x']
    closed_price = float(candle['c'])
    volume = candle['v']

    if is_candle_closed:
        close_prices.append(float(closed_price))
        volumes.append(float(volume))
        np_closes = numpy.array(close_prices)
        np_volumes = numpy.array(volumes)
        rsi = talib.RSI(np_closes, RSI_PERIOD)
        obv = talib.OBV(np_closes, np_volumes)
        ma = talib.MA(np_closes, RSI_PERIOD)
        macd, signal, macd_diff = talib.MACD(np_closes, fastperiod=12, slowperiod=26, signalperiod=9)
        prev_rsi = rsi[-2]
        # print('prev rsi {} '.format(prev_rsi))
        # print('rsi {} '.format(rsi[-1]))
        # print('prev cl price  {} '.format(close_prices[-2]))
        # print('cl price {} '.format(closed_price))
        # print('ma {} '.format(ma[-1]))
        # print('prev obv {} '.format(obv[-2]))
        # print('obv {} '.format(obv[-1]))
        # print('rsi < oversold < prev_rsi {} '.format((prev_rsi < RSI_OVERSOLD < rsi[-1])))
        # print('close_price >= ma {} '.format((closed_price >= ma[-1])))
        # print('prev_obv < obv {} '.format((obv[-2] < obv[-1])))
        # print('prev_c < c {} '.format((close_prices[-2] < closed_price)))
        print('rsi = {}, closed_price = {}, macd  = {} ,signal {},  diff =  {}, macd upcross? {}'.format(closed_price, rsi[-1], macd[-1], signal[-1],
                                                                                      macd_diff[-1],macd[-1] > signal[-1] and macd[-2] <= signal[-2]))
        print("----")

        if order:
            if order.status != ORDER_STATUS_FILLED:
                status = client.get_order(symbol=symbol, orderId=order.orderId)
                repository.update_order_status(order_id=order.orderId, status=status)
                return

            diff = closed_price - order['price']
            print("diff = {}".format(diff))
            if diff >= 5:
                print('sell!')
                sell_order = place_order(client, symbol, Client.SIDE_SELL, closed_price, order.executedQty)
                repository.save_order(order=order)
                repository.update_deal(order, sell_order)
                order = None
        else:
            if rsi[-1] < RSI_OVERSOLD \
                    and macd[-1] > signal[-1] and macd[-2] <= signal[-2] and macd[-1] < 0:
                qty = round(START_CASH / closed_price, 5)
                print('buy! qty = {}'.format(qty))
                order = place_order(client, symbol, Client.SIDE_BUY, closed_price, float(qty))
                repository.save_order(order=order)
                repository.save_deal(order)


def on_error(ws, error):
    print(error)


def on_close(ws, txt, error):
    print("### closed ### {}".format(ws))


print('start listening {}'.format(symbol))

# order = place_order(client, symbol, Client.SIDE_BUY,float(36300), 0.001684)
# order = {'symbol': 'BTCUSDT', 'orderId': 6183087675, 'orderListId': -1, 'clientOrderId': 'hzf8ut8BgIrCUh7Ey4kdgC', 'transactTime': 1622133593112, 'price': '38900.00000000', 'origQty': '0.00168400', 'executedQty': '0.00168400', 'cummulativeQuoteQty': '65.42289480', 'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'BUY', 'fills': [{'price': '38849.70000000', 'qty': '0.00168400', 'commission': '0.00000168', 'commissionAsset': 'BTC', 'tradeId': 875740731}]}

twm = ThreadedWebsocketManager(api_key=API_KEY, api_secret=API_SECRET)
twm.start()
twm.start_kline_socket(callback=handle_socket_message, symbol=symbol, interval=KLINE_INTERVAL_15MINUTE)

SOCKET = 'wss://stream.binance.com:443/ws/btcusdt@kline_1m'
websocket.enableTrace(False)
ws = websocket.WebSocketApp(SOCKET,
                            on_message=handle_socket_message,
                            on_error=on_error,
                            on_close=on_close)
ws.run_forever()
