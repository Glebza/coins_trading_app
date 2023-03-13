import logging
from binance.enums import *
from glebza.tradeapp.src.repository.binance_bot_repository import BinanceBotRepository

repository = BinanceBotRepository()


def open_deal(client, symbol, closed_price, qty):
    order = __execute_order(client, closed_price, float(qty), repository, SIDE_BUY, symbol)
    if order['status'] != ORDER_STATUS_FILLED:
        logging.info('Buy failed!')
    else:
        logging.info('Buy successful!')
        repository.save_deal(order)
    return order


def close_deal(client, symbol, closed_price, order):
    sell_order = __execute_order(client, closed_price, order['executedQty'], repository, SIDE_SELL, symbol)
    if sell_order['status'] != ORDER_STATUS_FILLED:
        logging.info('Sell failed!')
    else:
        logging.info('Sell successful!')
        repository.update_deal(order, sell_order)
    return sell_order


def __execute_order(client, closed_price, qty, repository, side, symbol):
    price = closed_price
    order_id = __place_order(client,
                           symbol,
                           side,
                           ORDER_TYPE_LIMIT,
                           price,
                           qty)['orderId']
    order = client.get_order(symbol=symbol, orderId=order_id)
    if order['status'] == ORDER_STATUS_FILLED:
        repository.save_order(order=order)
    return order


def __place_order(client, symbol, side, type, price, quantity):
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


def update_order_status(client, order, symbol):
    if order:
        if order['status'] != ORDER_STATUS_FILLED:
            order = client.get_order(symbol=symbol, orderId=order['orderId'])
            status = order['status']
            repository.update_order_status(order_id=order['orderId'], status=status,
                                           executedqty=order['executedQty'])

    return order


def get_open_deal_order(symbol):
    return repository.get_open_deal_order(symbol)

