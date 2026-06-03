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

Entry scripts still under `src/` (import from here):

- `binance_bot.py` — live Binance bot using legacy strategies + service
- `signal_bot.py` — futures signal bot using legacy `signal_service`

Imports use `glebza.tradeapp.legacy.*` (repo root on `PYTHONPATH`).
