#!/usr/bin/env bash
# Runs ON the remote server (invoked by deploy-transition-service.sh over SSH).
# Requires: glebza/transition_service and glebza/tradeapp/db rsynced under GLEBZA_ROOT.
set -euo pipefail

GLEBZA_ROOT="${GLEBZA_ROOT:-/opt/glebza}"
TRADEAPP_DIR="${TRADEAPP_DIR:-${GLEBZA_ROOT}/tradeapp}"
TRANSITION_SERVICE_DIR="${TRANSITION_SERVICE_DIR:-${GLEBZA_ROOT}/transition_service}"
DB_DIR="${DB_DIR:-${TRADEAPP_DIR}/db}"
DEPLOY_DIR="${DEPLOY_DIR:-${GLEBZA_ROOT}/deploy}"
LIQUIBASE_HOME="${LIQUIBASE_HOME:-${GLEBZA_ROOT}/liquibase}"
GLEBZA_LIQUIBASE_VERSION="${GLEBZA_LIQUIBASE_VERSION:-${LIQUIBASE_VERSION:-4.31.1}}"
unset LIQUIBASE_VERSION
ENV_FILE="${ENV_FILE:-/etc/glebza/transition-service.env}"
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

log() {
  echo "==> $*"
}

install_os_packages() {
  if command -v python3 >/dev/null 2>&1 && python3 -m venv --help >/dev/null 2>&1; then
    return
  fi
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

  sudo sed -i "s|localhost|${PG_HOST}|g" "${DB_DIR}/liquibase.bootstrap.properties"
  sudo sed -i "s|localhost|${PG_HOST}|g" "${DB_DIR}/liquibase.properties"
  sudo sed -i "s|localhost:5432|${PG_HOST}:${PG_PORT}|g" "${DB_DIR}/liquibase.bootstrap.properties"
  sudo sed -i "s|localhost:5432|${PG_HOST}:${PG_PORT}|g" "${DB_DIR}/liquibase.properties"
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

install_transition_service_venv() {
  log "create Python venv and install transition_service dependencies in ${TRANSITION_SERVICE_DIR}"
  python3 -m venv "${TRANSITION_SERVICE_DIR}/.venv"
  "${TRANSITION_SERVICE_DIR}/.venv/bin/pip" install --upgrade pip
  "${TRANSITION_SERVICE_DIR}/.venv/bin/pip" install -r "${TRANSITION_SERVICE_DIR}/requirements.txt"
}

write_transition_service_env() {
  log "write ${ENV_FILE}"
  sudo mkdir -p /etc/glebza
  sudo tee "${ENV_FILE}" >/dev/null <<EOF
GLEBZA_ROOT=${GLEBZA_ROOT}
TRADEAPP_DIR=${TRADEAPP_DIR}
TRANSITION_SERVICE_DIR=${TRANSITION_SERVICE_DIR}

DATABASE_URL=postgresql://trader:${TRADER_PASSWORD}@${PG_HOST}:${PG_PORT}/backtest
DATABASE_DEFAULT_SCHEMA=backtests

LIVE_DATABASE_URL=postgresql://trader:${TRADER_PASSWORD}@${PG_HOST}:${PG_PORT}/traderdb
LIVE_DATABASE_DEFAULT_SCHEMA=public
EOF
  sudo chown "${GLEBZA_RUN_USER}:${GLEBZA_RUN_USER}" "${ENV_FILE}"
  sudo chmod 600 "${ENV_FILE}"
}

print_summary() {
  log "transition_service install finished"
  log "paths: GLEBZA_ROOT=${GLEBZA_ROOT} TRANSITION_SERVICE_DIR=${TRANSITION_SERVICE_DIR} DB_DIR=${DB_DIR}"
  log ""
  log "list backtest runs:"
  log "  cd ${TRANSITION_SERVICE_DIR} && set -a && source ${ENV_FILE} && set +a && export PYTHONPATH=src"
  log "  .venv/bin/python -m transition_service list-runs"
  log ""
  log "promote a completed run to public:"
  log "  .venv/bin/python -m transition_service promote --run-id <id>"
}

main() {
  log "glebza transition_service remote install"
  install_os_packages
  install_liquibase
  write_liquibase_properties
  run_liquibase_bootstrap
  run_liquibase_trader
  install_transition_service_venv
  write_transition_service_env
  print_summary
}

main "$@"
