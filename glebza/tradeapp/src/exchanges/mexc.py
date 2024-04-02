from pymexc import futures

api_key = "YOUR API KEY"
api_secret = "YOUR API SECRET KEY"


def handle_message(message):
    # handle websocket message
    print(message)

    # FUTURES V1

    # initialize HTTP client
    futures_client = futures.HTTP(api_key=api_key, api_secret=api_secret)
    # initialize WebSocket client
    ws_futures_client = futures.WebSocket(api_key=api_key, api_secret=api_secret)

    # make http request to api
    print(futures_client.index_price("MX_USDT"))

    # create websocket connection to public channel (sub.tickers)
    # all messages will be handled by function `handle_message`
    ws_futures_client.tickers_stream(handle_message)

    # loop forever for save websocket connection
    while True:
        pass