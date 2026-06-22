# glebza remote deploy — daily_loader

Deploy `daily_loader` to a server that **already runs PostgreSQL**. The script does **not** reinstall or reset Postgres.

## What it does

1. **Rsync** full project trees (paths from `GLEBZA_ROOT`, `TRADEAPP_DIR`, `DAILY_LOADER_DIR`)
2. **Install** Python venv + `daily_loader` dependencies
3. **Check** T-Invest API (`check-tinvest`)
4. **Install** Java + Liquibase CLI
5. **Bootstrap DB** (idempotent): role `trader`, databases `traderdb` / `backtest`
6. **Migrate** from `${TRADEAPP_DIR}/db/changelog` → `backtest` / `backtests`
7. **Write** `/etc/glebza/daily-loader.env`
8. **Install** systemd timer (`daily-loader.service` + `.timer`)

**Not run by deploy:** initial historical backfill — run manually after install (see [After deploy](#after-deploy)). Automated backfill in deploy is **TODO**.

## One-time server setup (root)

Run **once on the CentOS server as root** (console or SSH as root). Required so `trader` can rsync into `/opt/glebza` and `remote-install.sh` can run `dnf`, write `/etc/glebza/`, and install systemd units **without an interactive sudo password**.

```bash
mkdir -p /opt/glebza
chown -R trader:trader /opt/glebza

cat <<'EOF' >/etc/sudoers.d/trader-deploy
trader ALL=(ALL) NOPASSWD: ALL
EOF
chmod 440 /etc/sudoers.d/trader-deploy
```

Verify as `trader`:

```bash
sudo -n true && echo "passwordless sudo OK"
mkdir -p /opt/glebza/test && rmdir /opt/glebza/test && echo "write OK"
```

For tighter security, replace `NOPASSWD: ALL` with only the commands `remote-install.sh` needs (`dnf`, `systemctl`, `tee` to `/etc/glebza`, etc.).

## Environment variables before deploy

Set these in **`glebza/deploy/deploy.env`** on your laptop (copy from `env/deploy.env.example`), then run `./glebza/deploy/deploy-daily-loader.sh`.

### Required

| Variable | Where used |
|----------|------------|
| `DEPLOY_REMOTE` | SSH target, e.g. `centos@203.0.113.10` (laptop deploy only) |
| `PG_SUPERUSER_PASSWORD` | Liquibase bootstrap against existing Postgres |
| `TRADER_PASSWORD` | Creates/uses `trader` role; written into `DATABASE_URL` on server |
| `INVEST_TOKEN` | T-Invest API; checked on server before DB migrations |

### Optional (defaults shown)

| Variable | Default | Purpose |
|----------|---------|---------|
| `GLEBZA_ROOT` | `/opt/glebza` | Root install directory on server |
| `TRADEAPP_DIR` | `${GLEBZA_ROOT}/tradeapp` | tradeapp tree (Liquibase changelogs in `db/`) |
| `DAILY_LOADER_DIR` | `${GLEBZA_ROOT}/daily_loader` | daily_loader app + venv |
| `DB_DIR` | `${TRADEAPP_DIR}/db` | Liquibase working directory (remote-install only) |
| `PG_HOST` | `localhost` | Postgres host |
| `PG_PORT` | `5432` | Postgres port |
| `PG_SUPERUSER` | `postgres` | Postgres superuser name |
| `GLEBZA_LIQUIBASE_VERSION` | `4.31.1` | Liquibase CLI version to install |
| `ENV_FILE` | `/etc/glebza/daily-loader.env` | Runtime env file path on server |

### Server-side only (created by deploy)

After install, `/etc/glebza/daily-loader.env` contains paths + `DATABASE_URL`, `INVEST_TOKEN`, and `DAILY_LOADER_*` tuning vars. You do **not** need to create this file before deploy.

### Prerequisites (non-env)

| Item | Notes |
|------|--------|
| Remote SSH | passwordless `ssh user@host` recommended |
| PostgreSQL | already installed on the server |
| T-Invest API | reachable from the server (checked during deploy) |
| sudo | passwordless sudo for `trader` (see [One-time server setup](#one-time-server-setup-root)) |

## Quick start (from your laptop)

```bash
cd /path/to/coins_trading_app

cp glebza/deploy/env/deploy.env.example glebza/deploy/deploy.env
# edit: DEPLOY_REMOTE, PG_SUPERUSER_PASSWORD, TRADER_PASSWORD, INVEST_TOKEN

chmod +x glebza/deploy/deploy-daily-loader.sh glebza/deploy/remote-install.sh
./glebza/deploy/deploy-daily-loader.sh
```

## Run install on the server only

If files are already rsynced under `GLEBZA_ROOT`:

```bash
export PG_SUPERUSER_PASSWORD=...
export TRADER_PASSWORD=...
export INVEST_TOKEN=...
export GLEBZA_ROOT=/opt/glebza
export TRADEAPP_DIR=/opt/glebza/tradeapp
export DAILY_LOADER_DIR=/opt/glebza/daily_loader
./glebza/deploy/deploy-daily-loader.sh --on-server
```

## After deploy

SSH as **`trader`** (same user as deploy). The env file is owned by that user (`chmod 600`).

Initial data load is **manual** (granular CLI):

```bash
cd /opt/glebza/daily_loader
set -a && source /etc/glebza/daily-loader.env && set +a
export PYTHONPATH=src

.venv/bin/python -m daily_loader sync-shares
.venv/bin/python -m daily_loader load-klines \
  --start-dt 2020-01-01T00:00:00+00:00 --end-dt 2026-06-01T00:00:00+00:00
.venv/bin/python -m daily_loader load-dividends \
  --start-dt 2020-01-01T00:00:00+00:00 --end-dt 2026-06-01T00:00:00+00:00
.venv/bin/python -m daily_loader load-ruonia \
  --start-dt 2020-01-01T00:00:00+00:00 --end-dt 2026-06-01T00:00:00+00:00
```

Daily incremental job (timer or manual):

```bash
sudo systemctl start daily-loader.service
journalctl -u daily-loader.service -n 100
```

If `/etc/glebza/daily-loader.env` is still `root:root` from an older deploy, fix once:

```bash
sudo chown trader:trader /etc/glebza/daily-loader.env
sudo chmod 600 /etc/glebza/daily-loader.env
```

**TODO:** wire automated initial backfill into deploy (or a dedicated `systemctl start daily-loader-backfill.service` flow once `BACKFILL_*` env is standardized).

## Portfolio backtest on the server

Script: `${GLEBZA_ROOT}/deploy/run-backtest.sh` — sets `PYTHONPATH`, sources `/etc/glebza/daily-loader.env`, creates `_pyroot` symlink if missing.

**Foreground** (output to terminal):

```bash
/opt/glebza/deploy/run-backtest.sh
```

**Background** (log + pid files):

```bash
/opt/glebza/deploy/run-backtest.sh --background --name oos-2020-2026
tail -f /opt/glebza/logs/backtest-oos-2020-2026.log
kill $(cat /opt/glebza/logs/backtest-oos-2020-2026.pid)
```

**Custom CLI args** (replace defaults):

```bash
/opt/glebza/deploy/run-backtest.sh --background --name custom -- \
  --interval 1d \
  --start-dt 2020-01-01T00:00:00+00:00 \
  --end-dt 2026-01-01T00:00:00+00:00 \
  --step 1y \
  --strategy-id 1 \
  --plot-path /opt/glebza/reports/my-run.png
```

Outputs:

| Artifact | Path |
|----------|------|
| Log | `/opt/glebza/logs/backtest-<name>.log` |
| PID | `/opt/glebza/logs/backtest-<name>.pid` |
| Plot PNG | `/opt/glebza/reports/portfolio-backtest-<name>.png` (default name) |
| DB row | `backtests.backtest_runs` (`backtest_run_id=` in log) |

Requires `tradeapp/.venv` with pandas, matplotlib, psycopg2, `t-tech-investments` (see script error message if missing).

## Layout on server

```text
/opt/glebza/                    GLEBZA_ROOT
  daily_loader/                 DAILY_LOADER_DIR
  tradeapp/                     TRADEAPP_DIR
    db/changelog/               Liquibase changesets
  liquibase/
  deploy/
    run-backtest.sh           # framework.backtest wrapper (foreground/background)
/etc/glebza/daily-loader.env    ENV_FILE
/etc/systemd/system/daily-loader.service
```

## Safety

- Bootstrap changeSets use `preConditions` / `onFail: MARK_RAN` — existing Postgres is not reset.
- App migrations are forward-only Liquibase `update`.
