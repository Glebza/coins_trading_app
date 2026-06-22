# transition_service

Standalone CLI to **list** completed backtest runs and **promote** a run’s strategy + portfolio from the backtest database (`backtest` / schema `backtests`) into the live/paper database (`traderdb` / schema `public`).

Sibling of `daily_loader` and `tradeapp`. No dependency on `tradeapp` Python imports.

## Layout

```text
glebza/transition_service/
  src/
    transition_service/   # CLI + promotion logic
    repository/           # backtest reads, public writes
  requirements.txt
```

## Env

```bash
# Source (research)
DATABASE_URL=postgresql://trader:...@localhost:5432/backtest
DATABASE_DEFAULT_SCHEMA=backtests

# Target (live/paper)
LIVE_DATABASE_URL=postgresql://trader:...@localhost:5432/traderdb
LIVE_DATABASE_DEFAULT_SCHEMA=public
```

On the server after deploy: `/etc/glebza/transition-service.env`

## CLI

| Command | Purpose |
|---------|---------|
| `list-runs` | Print backtest runs: id, kline interval, annualised return, Sharpe, started_at, status |
| `promote --run-id N` | Copy exchange, instruments (if missing), strategy, portfolio, rules to `public` |
| `promote --run-id N --dry-run` | Validate without writing to `public` |

### Examples

```bash
cd glebza/transition_service
export PYTHONPATH=src
python -m transition_service list-runs
python -m transition_service list-runs --status completed --limit 20
python -m transition_service promote --run-id 3
python -m transition_service promote --run-id 3 --dry-run
```

## What `promote` copies

From the completed `backtest_runs` row:

1. **exchange** — upsert by `code` into `public.exchange`
2. **instruments** — for each portfolio ticker missing in `public.instruments`, copy `instruments` + `instrument_share` from backtests
3. **strategy** — insert into `public.strategy` (Carver account defaults)
4. **portfolio** + **portfolio_instruments** — insert with remapped instrument ids
5. **strategy_portfolio** — link strategy to portfolio
6. **strategy_rules** — map `rule_variations` by `(rules.code, rule_variations.name)` (Liquibase seeds must exist in public)

Returns new `public.strategy.id` and `public.portfolio.id` in logs.

**Note:** `public` uses table name `strategy`; backtests uses `carver_strategy`. Live trading code that reads `carver_strategy` still expects the backtests schema — point `DATABASE_URL` at traderdb and align table names separately when wiring live deployment.

## Deploy

From repo root (same `deploy.env` as daily_loader, but `INVEST_TOKEN` is not required):

```bash
./glebza/deploy/deploy-transition-service.sh
# or
./glebza/deploy/deploy-transition-service.sh trader@155.212.185.97
```

Server paths:

```text
/opt/glebza/transition_service/
/opt/glebza/tradeapp/db/          # Liquibase changelogs (traderdb migrations)
/etc/glebza/transition-service.env
```

After deploy:

```bash
cd /opt/glebza/transition_service
set -a && source /etc/glebza/transition-service.env && set +a
export PYTHONPATH=src
.venv/bin/python -m transition_service list-runs
.venv/bin/python -m transition_service promote --run-id 1
```
