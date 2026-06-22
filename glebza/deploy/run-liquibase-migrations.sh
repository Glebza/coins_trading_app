#!/usr/bin/env bash
# Run all Liquibase migrations on the server (bootstrap + traderdb + backtest).
#
# Usage on server:
#   PG_SUPERUSER_PASSWORD='...' TRADER_PASSWORD='...' \
#     /opt/glebza/deploy/run-liquibase-migrations.sh
#
# Or after daily_loader deploy (reads trader password from DATABASE_URL):
#   set -a && source /etc/glebza/daily-loader.env && set +a
#   PG_SUPERUSER_PASSWORD='...' /opt/glebza/deploy/run-liquibase-migrations.sh
set -euo pipefail

GLEBZA_ROOT="${GLEBZA_ROOT:-/opt/glebza}"
TRADEAPP_DIR="${TRADEAPP_DIR:-${GLEBZA_ROOT}/tradeapp}"
DB_DIR="${DB_DIR:-${TRADEAPP_DIR}/db}"
DEPLOY_DIR="${DEPLOY_DIR:-${GLEBZA_ROOT}/deploy}"
LIQUIBASE_HOME="${LIQUIBASE_HOME:-${GLEBZA_ROOT}/liquibase}"
GLEBZA_LIQUIBASE_VERSION="${GLEBZA_LIQUIBASE_VERSION:-4.31.1}"
unset LIQUIBASE_VERSION

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

extract_trader_password_from_url() {
  python3 - <<'PY'
import os, re
url = os.environ.get("DATABASE_URL", "")
m = re.match(r"postgresql://[^:]+:([^@]+)@", url)
print(m.group(1) if m else "")
PY
}

log() {
  echo "==> $*"
}

ensure_liquibase_properties() {
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

run_bootstrap() {
  log "Liquibase bootstrap (postgres: role trader + databases traderdb/backtest)"
  (
    cd "${DB_DIR}"
    export LIQUIBASE_COMMAND_PASSWORD="${PG_SUPERUSER_PASSWORD}"
    export JAVA_OPTS="-Dtrader.password=${TRADER_PASSWORD}"
    "${LIQUIBASE_HOME}/liquibase" --defaultsFile=liquibase.bootstrap.properties update
  )
}

run_trader() {
  log "Liquibase traderdb (public schema — strategy, portfolio, exchange, ...)"
  (
    cd "${DB_DIR}"
    export LIQUIBASE_COMMAND_PASSWORD="${TRADER_PASSWORD}"
    "${LIQUIBASE_HOME}/liquibase" --defaultsFile=liquibase.properties update
  )
}

run_backtest() {
  log "Liquibase backtest (backtests schema)"
  (
    cd "${DB_DIR}"
    export LIQUIBASE_COMMAND_PASSWORD="${TRADER_PASSWORD}"
    "${LIQUIBASE_HOME}/liquibase" --defaultsFile=liquibase.backtest.properties update
  )
}

main() {
  if [[ -z "${TRADER_PASSWORD:-}" && -n "${DATABASE_URL:-}" ]]; then
    TRADER_PASSWORD="$(extract_trader_password_from_url)"
    export TRADER_PASSWORD
  fi

  require_env PG_SUPERUSER_PASSWORD
  require_env TRADER_PASSWORD

  if [[ ! -x "${LIQUIBASE_HOME}/liquibase" ]]; then
    echo "Liquibase not found at ${LIQUIBASE_HOME}/liquibase" >&2
    exit 1
  fi

  ensure_liquibase_properties
  run_bootstrap
  run_trader
  run_backtest
  log "all migrations finished"
}

main "$@"
