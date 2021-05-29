from datetime import datetime, timedelta
import json, pprint, numpy, talib, os
from binance import Client, ThreadedWebsocketManager, ThreadedDepthCacheManager
from binance import ThreadedWebsocketManager
from binance.enums import *
from glebza.tradeapp.src.repository.binance_bot_repository import BinanceBotRepository
from binance.exceptions import BinanceAPIException

API_KEY = os.environ['API_KEY']
API_SECRET = os.environ['API_SECRET']
client = Client(API_KEY, API_SECRET)
symbol = 'BTCUSDT'
RSI_PERIOD = 14
RSI_OVERSOLD = 40
RSI_OVERBOUGHT = 70
START_CASH = 150


def warm_up(client, ticker):
    print(ticker)
    volumes = []
    closes = []
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=1)).strftime("%d/%m/%Y, %H:%M:%S")
    klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_15MINUTE, start_date,
                                          end_date.strftime("%d/%m/%Y, %H:%M:%S"))
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


warm_data = warm_up(symbol)
volumes = warm_data[1]
close_prices = warm_data[0]
print(close_prices)
in_position = False
order = None



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
def handle_socket_message(msg):
    global in_position
    global order
    repository = BinanceBotRepository()
    candle = msg['k']
    is_candle_closed = candle['x']
    closed_price = float(candle['c'])
    volume = candle['v']

    if order is not None:
        order = client.get_order(symbol=symbol, orderId=order.orderId)
        if order.status == ORDER_STATUS_FILLED:
            repository.update_order_status(order_id=order.orderId, status=ORDER_STATUS_FILLED)
            if order.side == SIDE_BUY:
                in_position = True
            else:
                order = None

    if is_candle_closed:
        print(msg)
        close_prices.append(float(closed_price))
        volumes.append(float(volume))
        print(close_prices)
        np_closes = numpy.array(close_prices)
        np_volumes = numpy.array(volumes)
        rsi = talib.RSI(np_closes, RSI_PERIOD)
        obv = talib.OBV(np_closes, np_volumes)
        ma = talib.MA(np_closes, RSI_PERIOD)
        prev_rsi = rsi[-2]
        print('prev rsi {} '.format(prev_rsi))
        print('rsi {} '.format(rsi[-1]))
        print('prev cl price  {} '.format(close_prices[-2]))
        print('cl price {} '.format(closed_price))
        print('ma {} '.format(ma[-1]))
        print('prev obv {} '.format(obv[-2]))
        print('obv {} '.format(obv[-1]))
        print('rsi < oversold < prev_rsi {} '.format((prev_rsi < RSI_OVERSOLD < rsi[-1])))
        print('close_price >= ma {} '.format((closed_price >= ma[-1])))
        print('prev_obv < obv {} '.format((obv[-2] < obv[-1])))
        print('prev_c < c {} '.format((close_prices[-2] < closed_price)))
        if in_position:
            diff = (closed_price - order.price) / order.price
            if diff < float(-0.05) or rsi[0] > RSI_OVERBOUGHT and closed_price < ma[0]:
                print('sell!')
                order = place_order(client, symbol, Client.SIDE_SELL, closed_price * 0.99, order.executedQty)
                repository.save_order(order=order)
                in_position = False
        else:
            if prev_rsi < RSI_OVERSOLD < rsi[-1] and closed_price >= ma[-1] \
                    and obv[-2] < obv[-1] and close_prices[-2] < closed_price:
                qty = START_CASH / closed_price
                print('buy! qty = {}'.format(qty))
                order = place_order(client, symbol, Client.SIDE_BUY, closed_price, float(qty))
                repository.save_order(order=order)


print('start listening {}'.format(symbol))
# repository = BinanceBotRepository()
# order = place_order(client, symbol, Client.SIDE_BUY,float(36300), 0.001684)
# order = {'symbol': 'BTCUSDT', 'orderId': 6183087675, 'orderListId': -1, 'clientOrderId': 'hzf8ut8BgIrCUh7Ey4kdgC', 'transactTime': 1622133593112, 'price': '38900.00000000', 'origQty': '0.00168400', 'executedQty': '0.00168400', 'cummulativeQuoteQty': '65.42289480', 'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'BUY', 'fills': [{'price': '38849.70000000', 'qty': '0.00168400', 'commission': '0.00000168', 'commissionAsset': 'BTC', 'tradeId': 875740731}]}
twm = ThreadedWebsocketManager(api_key=API_KEY, api_secret=API_SECRET)
twm.start()
twm.start_kline_socket(callback=handle_socket_message, symbol=symbol, interval=KLINE_INTERVAL_15MINUTE)
