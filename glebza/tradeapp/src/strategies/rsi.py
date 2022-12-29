def rsi_strategy:
    if order is None and not in_position:
        order = repository.get_open_deal_order(symbol)
        if order is not None:
            in_position = True

    if in_position:

        if order.status != ORDER_STATUS_FILLED:
            status = client.get_order(symbol=symbol, orderId=order.orderId)
            repository.update_order_status(order_id=order.orderId, status=status)
            return

        diff = (closed_price - order.price) / order.price
        if diff < float(-0.05) or rsi[0] > RSI_OVERBOUGHT and closed_price < ma[0]:
            print('sell!')
            sell_order = place_order(client, symbol, Client.SIDE_SELL, closed_price * 0.99, order.executedQty)
            repository.save_order(order=order)
            repository.update_deal(order, sell_order)
            in_position = False
    else:
        if prev_rsi < RSI_OVERSOLD < rsi[-1] and closed_price >= ma[-1] \
                and obv[-2] < obv[-1] and close_prices[-2] < closed_price:
            qty = round(START_CASH / closed_price, 5)
            print('buy! qty = {}'.format(qty))
            order = place_order(client, symbol, Client.SIDE_BUY, closed_price, float(qty))
            repository.save_order(order=order)
            repository.save_deal(order)