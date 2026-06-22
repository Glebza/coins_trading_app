#!/usr/bin/env bash
# Runs ON the remote server (invoked by deploy-daily-loader.sh over SSH).
# Requires: glebza/daily_loader and glebza/tradeapp rsynced under GLEBZA_ROOT.
set -euo pipefail

GLEBZA_ROOT="${GLEBZA_ROOT:-/opt/glebza}"
TRADEAPP_DIR="${TRADEAPP_DIR:-${GLEBZA_ROOT}/tradeapp}"
DAILY_LOADER_DIR="${DAILY_LOADER_DIR:-${GLEBZA_ROOT}/daily_loader}"
DB_DIR="${DB_DIR:-${TRADEAPP_DIR}/db}"
DEPLOY_DIR="${DEPLOY_DIR:-${GLEBZA_ROOT}/deploy}"
LIQUIBASE_HOME="${LIQUIBASE_HOME:-${GLEBZA_ROOT}/liquibase}"
GLEBZA_LIQUIBASE_VERSION="${GLEBZA_LIQUIBASE_VERSION:-${LIQUIBASE_VERSION:-4.31.1}}"
unset LIQUIBASE_VERSION
ENV_FILE="${ENV_FILE:-/etc/glebza/daily-loader.env}"
GLEBZA_RUN_USER="${GLEBZA_RUN_USER:-$(whoami)}"

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_SUPERUSER="${PG_SUPERUSER:-postgres}"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "missing required env var: ${name}" >&2
    exit 1
  fi
}

require_env PG_SUPERUSER_PASSWORD
require_env TRADER_PASSWORD
require_env INVEST_TOKEN

log() {
  echo "==> $*"
}

install_os_packages() {
  log "install OS packages (Java, Python, curl, rsync)"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      ca-certificates curl rsync python3 python3-venv python3-pip \
      openjdk-17-jre-headless
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y curl rsync python3 java-17-openjdk-headless
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y curl rsync python3 java-17-openjdk-headless
  else
    echo "unsupported package manager; install Java 17+, Python 3.10+, curl, rsync manually" >&2
    exit 1
  fi
}

install_liquibase() {
  if [[ -x "${LIQUIBASE_HOME}/liquibase" ]]; then
    log "liquibase already installed at ${LIQUIBASE_HOME}"
    return
  fi

  log "install Liquibase ${GLEBZA_LIQUIBASE_VERSION} to ${LIQUIBASE_HOME}"
  sudo mkdir -p "${LIQUIBASE_HOME}"
  tmp="$(mktemp -d)"
  curl -fsSL \
    "https://github.com/liquibase/liquibase/releases/download/v${GLEBZA_LIQUIBASE_VERSION}/liquibase-${GLEBZA_LIQUIBASE_VERSION}.tar.gz" \
    -o "${tmp}/liquibase.tgz"
  sudo tar -xzf "${tmp}/liquibase.tgz" -C "${LIQUIBASE_HOME}"
  rm -rf "${tmp}"
  sudo chmod +x "${LIQUIBASE_HOME}/liquibase"
}

write_liquibase_properties() {
  log "write Liquibase properties under ${DB_DIR}"
  sudo cp "${DEPLOY_DIR}/liquibase/liquibase.bootstrap.properties.example" \
    "${DB_DIR}/liquibase.bootstrap.properties"
  sudo cp "${DEPLOY_DIR}/liquibase/liquibase.trader.properties.example" \
    "${DB_DIR}/liquibase.properties"
  sudo cp "${DEPLOY_DIR}/liquibase/liquibase.backtest.properties.example" \
    "${DB_DIR}/liquibase.backtest.properties"

  sudo sed -i "s|localhost|${PG_HOST}|g" "${DB_DIR}/liquibase.bootstrap.properties"
  sudo sed -i "s|localhost|${PG_HOST}|g" "${DB_DIR}/liquibase.properties"
  sudo sed -i "s|localhost|${PG_HOST}|g" "${DB_DIR}/liquibase.backtest.properties"
  sudo sed -i "s|localhost:5432|${PG_HOST}:${PG_PORT}|g" "${DB_DIR}/liquibase.bootstrap.properties"
  sudo sed -i "s|localhost:5432|${PG_HOST}:${PG_PORT}|g" "${DB_DIR}/liquibase.properties"
  sudo sed -i "s|localhost:5432|${PG_HOST}:${PG_PORT}|g" "${DB_DIR}/liquibase.backtest.properties"
}

run_liquibase_bootstrap() {
  log "Liquibase bootstrap (role trader + databases traderdb/backtest — idempotent)"
  (
    cd "${DB_DIR}"
    export LIQUIBASE_COMMAND_PASSWORD="${PG_SUPERUSER_PASSWORD}"
    export JAVA_OPTS="-Dtrader.password=${TRADER_PASSWORD}"
    "${LIQUIBASE_HOME}/liquibase" --defaultsFile=liquibase.bootstrap.properties update
  )
}

run_liquibase_trader() {
  log "Liquibase traderdb schema migrations (database traderdb / schema public)"
  (
    cd "${DB_DIR}"
    export LIQUIBASE_COMMAND_PASSWORD="${TRADER_PASSWORD}"
    "${LIQUIBASE_HOME}/liquibase" --defaultsFile=liquibase.properties update
  )
}

run_liquibase_backtest() {
  log "Liquibase backtest schema migrations (database backtest / schema backtests)"
  (
    cd "${DB_DIR}"
    export LIQUIBASE_COMMAND_PASSWORD="${TRADER_PASSWORD}"
    "${LIQUIBASE_HOME}/liquibase" --defaultsFile=liquibase.backtest.properties update
  )
}

install_daily_loader_venv() {
  log "create Python venv and install daily_loader dependencies in ${DAILY_LOADER_DIR}"
  python3 -m venv "${DAILY_LOADER_DIR}/.venv"
  "${DAILY_LOADER_DIR}/.venv/bin/pip" install --upgrade pip
  "${DAILY_LOADER_DIR}/.venv/bin/pip" install -r "${DAILY_LOADER_DIR}/requirements.txt"
}

check_tinvest_api() {
  log "check T-Invest API from this server (gRPC TLS + INVEST_TOKEN)"
  (
    cd "${DAILY_LOADER_DIR}"
    export PYTHONPATH=src
    export INVEST_TOKEN
    "${DAILY_LOADER_DIR}/.venv/bin/python" -m daily_loader check-tinvest
  )
}

write_daily_loader_env() {
  log "write ${ENV_FILE}"
  sudo mkdir -p /etc/glebza
  sudo tee "${ENV_FILE}" >/dev/null <<EOF
GLEBZA_ROOT=${GLEBZA_ROOT}
TRADEAPP_DIR=${TRADEAPP_DIR}
DAILY_LOADER_DIR=${DAILY_LOADER_DIR}

DATABASE_URL=postgresql://trader:${TRADER_PASSWORD}@${PG_HOST}:${PG_PORT}/backtest
DATABASE_DEFAULT_SCHEMA=backtests
INVEST_TOKEN=${INVEST_TOKEN}

DAILY_LOADER_KLINE_INTERVAL=1d
DAILY_LOADER_KLINE_LOOKBACK_DAYS=1
DAILY_LOADER_DIVIDEND_LOOKBACK_DAYS=365
DAILY_LOADER_RUONIA_LOOKBACK_DAYS=30
DAILY_LOADER_VOL_LOOKBACK_PERIOD=252
DAILY_LOADER_KLINE_REQUEST_DELAY_SECONDS=0.3
DAILY_LOADER_DIVIDEND_REQUEST_DELAY_SECONDS=0.5
DAILY_LOADER_RATE_LIMIT_RETRIES=3
DAILY_LOADER_RATE_LIMIT_FALLBACK_SLEEP_SECONDS=60
EOF
  sudo chown "${GLEBZA_RUN_USER}:${GLEBZA_RUN_USER}" "${ENV_FILE}"
  sudo chmod 600 "${ENV_FILE}"
}

install_systemd_units() {
  log "install systemd units"
  sudo cp "${DEPLOY_DIR}/systemd/daily-loader.service" /etc/systemd/system/
  sudo cp "${DEPLOY_DIR}/systemd/daily-loader.timer" /etc/systemd/system/
  sudo cp "${DEPLOY_DIR}/systemd/daily-loader-backfill.service" /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable daily-loader.timer
}

print_summary() {
  log "deploy install finished"
  log "paths: GLEBZA_ROOT=${GLEBZA_ROOT} TRADEAPP_DIR=${TRADEAPP_DIR} DAILY_LOADER_DIR=${DAILY_LOADER_DIR} DB_DIR=${DB_DIR}"
  log "daily timer enabled — incremental run: sudo systemctl start daily-loader.service"
  log "logs: journalctl -u daily-loader.service -n 100"
  log ""
  log "TODO: automated initial backfill during deploy is not run yet — load history manually:"
  log "  cd ${DAILY_LOADER_DIR} && set -a && source ${ENV_FILE} && set +a && export PYTHONPATH=src"
  log "  .venv/bin/python -m daily_loader sync-shares"
  log "  .venv/bin/python -m daily_loader load-klines --start-dt 2020-01-01T00:00:00+00:00 --end-dt <today>"
  log "  .venv/bin/python -m daily_loader load-dividends --start-dt ... --end-dt ..."
  log "  .venv/bin/python -m daily_loader load-ruonia --start-dt ... --end-dt ..."
  log "  # or later: sudo systemctl start daily-loader-backfill.service (after BACKFILL_* env is set)"
  log "backtest (foreground): ${GLEBZA_ROOT}/deploy/run-backtest.sh"
  log "backtest (background): ${GLEBZA_ROOT}/deploy/run-backtest.sh --background --name oos-2020-2026"
}

main() {
  log "glebza remote install — existing PostgreSQL is preserved (bootstrap changeSets are idempotent)"
  install_os_packages
  install_daily_loader_venv
  check_tinvest_api
  install_liquibase
  write_liquibase_properties
  run_liquibase_bootstrap
  run_liquibase_trader
  run_liquibase_backtest
  write_daily_loader_env
  install_systemd_units
  print_summary
}

main "$@"
