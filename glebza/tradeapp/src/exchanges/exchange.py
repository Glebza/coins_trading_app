from binance import Client
from binance.enums import *

class Exchange:
    client = None
    ws_address = None

    def __init__(self,api_key,api_secret,exchange_name):
        self.api_key = api_key
        self.api_secret = api_secret
        self.exchange_name = exchange_name

    def get_client(self)->object:
        return self.client

    def get_ws_spot_address(self):
        if self.exchange_name == "binance":
            return 'wss://stream.binance.com:443/ws/'
        if self.exchange_name == "mexc":
            return 'wss://wbs.mexc.com/ws/spot@public.kline.v3.api@'
        return self.ws_address


