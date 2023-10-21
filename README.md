структура модуля стратегия

на вход подаются свечки с закрывающими ценами и наличие позиции

на выходе дают команду WAIT,BUY,SELL и цену 


 variants:
 
in position:
 wait or sell 

not in position:
 wait or buy

формат candle 

{
  "e": "kline",         // Event type
  "E": 1672515782136,   // Event time
  "s": "BNBBTC",        // Symbol
  "k": {
    "t": 1672515780000, // Kline start time
    "T": 1672515839999, // Kline close time
    "s": "BNBBTC",      // Symbol
    "i": "1m",          // Interval
    "f": 100,           // First trade ID
    "L": 200,           // Last trade ID
    "o": "0.0010",      // Open price
    "c": "0.0020",      // Close price
    "h": "0.0025",      // High price
    "l": "0.0015",      // Low price
    "v": "1000",        // Base asset volume
    "n": 100,           // Number of trades
    "x": false,         // Is this kline closed?
    "q": "1.0000",      // Quote asset volume
    "V": "500",         // Taker buy base asset volume
    "Q": "0.500",       // Taker buy quote asset volume
    "B": "123456"       // Ignore
  }
}

Обучение нейронки:

Features:
['k_interval', 'close_price', 'volume', 'market_cap', 'atr',
             'rsi_15', 'rsi_9', 'macd', 'macd_sygnal', 'macd_diff', 'boll_low', 'boll_middle', 'boll_high']

Как посчитать market_cap для исторических данных?

возьмем период - месяц
тогда для расчета market_cap берем исторические данные за месяц + 1 день
далее market_cap = ∑ (Typical Price * Volume )
weightedAvgPrice = ∑ (Typical Price * Volume ) / ∑ Volume
Typical Price = Typical Price = (High + Low + Close) / 3


Берем 1m исторические данные 
на каждую минуту считаем market_cap за 24 часа



работа нейронки 
market_cap можно брать  через api client.get_ticker(symbol='BTCUSDT')
