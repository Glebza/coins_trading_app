import requests
import pandas as pd
from matplotlib import pyplot as plt

print(requests.get("https://iss.moex.com/iss/securities.json?q=Yandex").json())

j = requests.get("https://iss.moex.com/iss/securities.json?q=Yandex").json()
print("securities table columns:", j["securities"]["columns"])
data = [{k: r[i] for i, k in enumerate(j["securities"]["columns"])} for r in j["securities"]["data"]]
print(pd.DataFrame(data))


j = requests.get(
    "http://iss.moex.com/iss/engines/stock/markets/shares/securities/YNDX/candles.json"
    "?from=2023-05-25&till=2023-09-01&interval=24"
).json()
data = [{k: r[i] for i, k in enumerate(j["candles"]["columns"])} for r in j["candles"]["data"]]
frame = pd.DataFrame(data)
#plt.plot(list(frame["close"]))
#plt.savefig("shares.png")
