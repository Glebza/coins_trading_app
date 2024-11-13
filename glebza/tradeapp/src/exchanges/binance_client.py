from binance import Client
from binance.enums import *
import os

API_KEY = os.environ['API_KEY']
API_SECRET = os.environ['API_SECRET']

client = Client(API_KEY, API_SECRET)