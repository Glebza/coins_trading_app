# Legacy code

Pre-framework Binance/order stack and related utilities. **Not** used by
`python -m framework.backtest` (Carver-style framework under `src/framework/backtest/`).

| Path | Contents |
|------|----------|
| `backtest/` | DB-backed strategy backtest (`BUY`/`SELL`/`WAIT`), repositories, launcher |
| `strategies/` | `BollMacdRsiStrategy`, `DeviationsStrategy` (TA-Lib / tulipy) |
| `service/` | Binance order/market helpers, futures signal checks |
| `adapters/` | Telegram notifications (`telegram_adapter.py`) |
| `ingestion/` | MEXC WebSocket ingestion gateway |
| `engine/` | Neural-network experiment script (`neuro_engine.py`) |
| `repository/` | `BinanceBotRepository`, `SignalBotRepository` |
| `binance_bot.py` | Live Binance spot bot (Boll/MACD/RSI + order service) |
| `signal_bot.py` | Binance futures signal scanner |

Imports use `glebza.tradeapp.legacy.*` (repo root on `PYTHONPATH`). `binance_bot.py` also needs
`glebza/tradeapp/src` on `PYTHONPATH` for `exchanges.exchange`.

Example:

```bash
PYTHONPATH=".:glebza/tradeapp/src" \
API_KEY=... API_SECRET=... \
python glebza/tradeapp/legacy/binance_bot.py binance

PYTHONPATH="." \
python glebza/tradeapp/legacy/signal_bot.py
```
