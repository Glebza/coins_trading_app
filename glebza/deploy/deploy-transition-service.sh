#!/usr/bin/env bash
# Deploy glebza transition_service to a remote server.
#
# From repo root:
#   cp glebza/deploy/env/deploy.env.example glebza/deploy/deploy.env
#   # edit glebza/deploy/deploy.env (PG_SUPERUSER_PASSWORD, TRADER_PASSWORD)
#   ./glebza/deploy/deploy-transition-service.sh
#
# Or pass SSH target explicitly:
#   ./glebza/deploy/deploy-transition-service.sh trader@your-server
#
# Run install steps only on the server (files must already be in /opt/glebza):
#   ./glebza/deploy/deploy-transition-service.sh --on-server
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"
if [[ ! -f "${DEPLOY_ENV}" && -f "${SCRIPT_DIR}/env/deploy.env" ]]; then
  DEPLOY_ENV="${SCRIPT_DIR}/env/deploy.env"
fi

REMOTE=""
ON_SERVER=false

usage() {
  cat <<'EOF'
Usage:
  deploy-transition-service.sh [user@host]
  deploy-transition-service.sh --on-server

Environment (deploy.env or shell):
  DEPLOY_REMOTE                 SSH target (laptop deploy only)
  PG_SUPERUSER_PASSWORD         Postgres superuser password (bootstrap only)
  TRADER_PASSWORD               trader role password
  GLEBZA_ROOT                   optional (default /opt/glebza)
  TRADEAPP_DIR                  optional (default ${GLEBZA_ROOT}/tradeapp)
  TRANSITION_SERVICE_DIR        optional (default ${GLEBZA_ROOT}/transition_service)
  PG_HOST, PG_PORT              optional (default localhost:5432)
  PG_SUPERUSER                  optional (default postgres)
  GLEBZA_LIQUIBASE_VERSION      optional (default 4.31.1)
EOF
}

parse_args() {
  if [[ $# -eq 1 && "$1" == "--on-server" ]]; then
    ON_SERVER=true
    return
  fi
  if [[ $# -eq 1 && "$1" == "-h" || $# -eq 1 && "$1" == "--help" ]]; then
    usage
    exit 0
  fi
  if [[ $# -eq 1 ]]; then
    REMOTE="$1"
    return
  fi
  if [[ $# -eq 0 ]]; then
    return
  fi
  usage >&2
  exit 1
}

load_deploy_env() {
  if [[ -f "${DEPLOY_ENV}" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${DEPLOY_ENV}"
    set +a
  fi
  if [[ -z "${REMOTE}" && -n "${DEPLOY_REMOTE:-}" ]]; then
    REMOTE="${DEPLOY_REMOTE}"
  fi
}

require_remote_or_on_server() {
  if [[ "${ON_SERVER}" == true ]]; then
    return
  fi
  if [[ -z "${REMOTE}" ]]; then
    echo "set DEPLOY_REMOTE in deploy.env or pass user@host" >&2
    exit 1
  fi
}

rsync_to_remote() {
  local rsync_excludes=(
    --exclude '.venv/'
    --exclude '__pycache__/'
    --exclude '*.pyc'
  )
  local glebza_root="${GLEBZA_ROOT:-/opt/glebza}"
  local tradeapp_dir="${TRADEAPP_DIR:-${glebza_root}/tradeapp}"
  local transition_service_dir="${TRANSITION_SERVICE_DIR:-${glebza_root}/transition_service}"

  log "rsync transition_service -> ${REMOTE}:${transition_service_dir}/"
  ssh "${REMOTE}" "mkdir -p '${transition_service_dir}' '${tradeapp_dir}' '${glebza_root}/deploy'"
  rsync -avz --delete "${rsync_excludes[@]}" \
    "${REPO_ROOT}/glebza/transition_service/" "${REMOTE}:${transition_service_dir}/"

  log "rsync tradeapp/db -> ${REMOTE}:${tradeapp_dir}/ (Liquibase changelogs for traderdb)"
  rsync -avz --delete "${rsync_excludes[@]}" \
    "${REPO_ROOT}/glebza/tradeapp/db/" "${REMOTE}:${tradeapp_dir}/db/"

  log "rsync deploy assets -> ${REMOTE}:${glebza_root}/deploy/"
  rsync -avz "${SCRIPT_DIR}/remote-install-transition.sh" "${REMOTE}:${glebza_root}/deploy/"
  rsync -avz "${SCRIPT_DIR}/liquibase/" "${REMOTE}:${glebza_root}/deploy/liquibase/"
  rsync -avz "${SCRIPT_DIR}/env/transition-service.env.example" "${REMOTE}:${glebza_root}/deploy/env/"
  ssh "${REMOTE}" "chmod +x '${glebza_root}/deploy/remote-install-transition.sh'"
}

run_remote_install() {
  local glebza_root="${GLEBZA_ROOT:-/opt/glebza}"
  log "run remote-install-transition.sh on ${REMOTE}"
  ssh "${REMOTE}" \
    "PG_SUPERUSER_PASSWORD='${PG_SUPERUSER_PASSWORD}' \
     TRADER_PASSWORD='${TRADER_PASSWORD}' \
     PG_HOST='${PG_HOST:-localhost}' \
     PG_PORT='${PG_PORT:-5432}' \
     PG_SUPERUSER='${PG_SUPERUSER:-postgres}' \
     GLEBZA_ROOT='${glebza_root}' \
     TRADEAPP_DIR='${TRADEAPP_DIR:-${glebza_root}/tradeapp}' \
     TRANSITION_SERVICE_DIR='${TRANSITION_SERVICE_DIR:-${glebza_root}/transition_service}' \
     GLEBZA_LIQUIBASE_VERSION='${GLEBZA_LIQUIBASE_VERSION:-${LIQUIBASE_VERSION:-4.31.1}}' \
     ENV_FILE='${ENV_FILE:-/etc/glebza/transition-service.env}' \
     bash '${glebza_root}/deploy/remote-install-transition.sh'"
}

verify_remote_sudo() {
  if [[ "${ON_SERVER}" == true ]]; then
    if ! sudo -n true 2>/dev/null; then
      echo "passwordless sudo required on the server for remote-install-transition (dnf, /etc/glebza)." >&2
      exit 1
    fi
    return
  fi
  if ! ssh "${REMOTE}" "sudo -n true" 2>/dev/null; then
    echo "remote user on ${REMOTE} needs passwordless sudo for deploy." >&2
    exit 1
  fi
}

run_local_install() {
  log "run remote-install-transition.sh on this server"
  export PG_SUPERUSER_PASSWORD="${PG_SUPERUSER_PASSWORD:?}"
  export TRADER_PASSWORD="${TRADER_PASSWORD:?}"
  export PG_HOST="${PG_HOST:-localhost}"
  export PG_PORT="${PG_PORT:-5432}"
  export PG_SUPERUSER="${PG_SUPERUSER:-postgres}"
  export GLEBZA_ROOT="${GLEBZA_ROOT:-/opt/glebza}"
  export TRADEAPP_DIR="${TRADEAPP_DIR:-${GLEBZA_ROOT}/tradeapp}"
  export TRANSITION_SERVICE_DIR="${TRANSITION_SERVICE_DIR:-${GLEBZA_ROOT}/transition_service}"
  export GLEBZA_LIQUIBASE_VERSION="${GLEBZA_LIQUIBASE_VERSION:-${LIQUIBASE_VERSION:-4.31.1}}"
  export ENV_FILE="${ENV_FILE:-/etc/glebza/transition-service.env}"
  bash "${SCRIPT_DIR}/remote-install-transition.sh"
}

log() {
  echo "==> $*"
}

main() {
  parse_args "$@"
  load_deploy_env

  for var in PG_SUPERUSER_PASSWORD TRADER_PASSWORD; do
    if [[ -z "${!var:-}" ]]; then
      echo "missing ${var} — set it in ${DEPLOY_ENV} or your shell" >&2
      exit 1
    fi
  done

  if [[ "${ON_SERVER}" == true ]]; then
    verify_remote_sudo
    run_local_install
    exit 0
  fi

  require_remote_or_on_server
  verify_remote_sudo
  rsync_to_remote
  run_remote_install
  log "deploy finished"
}

main "$@"
