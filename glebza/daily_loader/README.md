# daily_loader

Standalone **once-a-day** ingestion service. Sibling of `tradeapp`; deploy on a remote server with systemd.

Loads into the shared PostgreSQL schema (`backtests`):

1. `sync-shares` — all T-Invest tradeable shares (`buy` + `sell` + `api_trade` flags)
2. `load-klines-all`
3. `load-dividends-all`
4. `load-ruonia`
5. `update-volatility`

**Daily run** (`run`):

1. `sync-shares` — upsert new tradeable tickers from T-Invest into the DB
2. Load klines/dividends/RUONIA/vol for **every share already in the DB** (default: **1-day** kline window)

**Initial historical backfill** (`backfill`): explicit `--start-dt` / `--end-dt` for every share in the DB (run once before daily `run`; new tickers discovered later only get 1 day until backfilled).

## Layout

```text
glebza/daily_loader/
  src/
    daily_loader/     # pipeline + steps
    repository/       # DB access for loader only
    services/         # T-Invest API, CBR RUONIA, gRPC TLS
  certs/              # Russian CA for T-Invest gRPC
  deploy/             # systemd unit + timer
```

No dependency on `tradeapp` Python imports.

## Env (`/etc/daily-loader.env`)

```bash
DATABASE_URL=postgresql://...
DATABASE_DEFAULT_SCHEMA=backtests
INVEST_TOKEN=...
```

Optional:

```bash
DAILY_LOADER_KLINE_INTERVAL=1d
DAILY_LOADER_KLINE_LOOKBACK_DAYS=1
DAILY_LOADER_DIVIDEND_LOOKBACK_DAYS=365
DAILY_LOADER_RUONIA_LOOKBACK_DAYS=30
DAILY_LOADER_VOL_LOOKBACK_PERIOD=252
DAILY_LOADER_KLINE_REQUEST_DELAY_SECONDS=0.3
DAILY_LOADER_DIVIDEND_REQUEST_DELAY_SECONDS=0.5
DAILY_LOADER_RATE_LIMIT_RETRIES=3
DAILY_LOADER_RATE_LIMIT_FALLBACK_SLEEP_SECONDS=60
```

## CLI

| Command | Purpose |
|---------|---------|
| `check-tinvest` | Verify T-Invest gRPC + token (no DB) |
| `sync-shares` | T-Invest share metadata → DB |
| `load-klines --start-dt … --end-dt …` | Klines for all DB shares |
| `load-dividends --start-dt … --end-dt …` | Dividends for all DB shares |
| `load-ruonia --start-dt … --end-dt …` | RUONIA from CBR |
| `run` | Daily cron (sync + 1-day window + volatility) |
| `backfill --start-dt … --end-dt …` | All steps in one go (initial setup shortcut) |

### Initial setup (manual steps)

```bash
PYTHONPATH=src DATABASE_URL=... DATABASE_DEFAULT_SCHEMA=backtests INVEST_TOKEN=... \
.venv/bin/python -m daily_loader sync-shares

.venv/bin/python -m daily_loader load-klines \
  --start-dt 2020-01-01T00:00:00+00:00 \
  --end-dt 2026-06-01T00:00:00+00:00

.venv/bin/python -m daily_loader load-dividends \
  --start-dt 2020-01-01T00:00:00+00:00 \
  --end-dt 2026-06-01T00:00:00+00:00

.venv/bin/python -m daily_loader load-ruonia \
  --start-dt 2020-01-01T00:00:00+00:00 \
  --end-dt 2026-06-01T00:00:00+00:00
```

Then enable the daily timer (`run` also refreshes volatility).

### Daily cron

```bash
.venv/bin/python -m daily_loader run
```

Or shortcut for full historical load:

```bash
.venv/bin/python -m daily_loader backfill \
  --start-dt 2020-01-01T00:00:00+00:00 \
  --end-dt 2026-06-01T00:00:00+00:00
```

## Local run

```bash
cd glebza/daily_loader
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Remote deploy (recommended)

See [`../deploy/README.md`](../deploy/README.md) — rsync `daily_loader` + `tradeapp` to `/opt/glebza/`, Liquibase migrations from `tradeapp/db/`, systemd, and initial backfill from 2020.

```bash
cp glebza/deploy/env/deploy.env.example glebza/deploy/deploy.env
# edit secrets
./glebza/deploy/deploy-daily-loader.sh ubuntu@your-server
```
