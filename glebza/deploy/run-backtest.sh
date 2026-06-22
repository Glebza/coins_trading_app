#!/usr/bin/env bash
# Run framework.backtest on the server (foreground or background with log + pid files).
#
# Examples:
#   /opt/glebza/deploy/run-backtest.sh --background
#   /opt/glebza/deploy/run-backtest.sh --background --name oos-2020-2026
#   /opt/glebza/deploy/run-backtest.sh -- --step 1y --streaming
#   tail -f /opt/glebza/logs/backtest-oos-2020-2026.log
set -euo pipefail

GLEBZA_ROOT="${GLEBZA_ROOT:-/opt/glebza}"
TRADEAPP_DIR="${TRADEAPP_DIR:-${GLEBZA_ROOT}/tradeapp}"
ENV_FILE="${ENV_FILE:-/etc/glebza/daily-loader.env}"
LOG_DIR="${LOG_DIR:-${GLEBZA_ROOT}/logs}"
REPORTS_DIR="${REPORTS_DIR:-${GLEBZA_ROOT}/reports}"
PYROOT="${GLEBZA_ROOT}/_pyroot"

BACKGROUND=false
RUN_NAME="${RUN_NAME:-oos-2020-2026}"
EXTRA_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  run-backtest.sh [--background] [--name RUN_NAME] [-- BACKTEST_ARGS...]

Options:
  --background   Detach with nohup; write log + pid under /opt/glebza/logs/
  --name NAME    Base name for log/pid/plot files (default: oos-2020-2026)
  --help         Show this help

Default backtest (when no extra args after --):
  expanding OOS 2020-2026, 1d, strategy-id 1, plot under /opt/glebza/reports/

Environment (optional overrides):
  GLEBZA_ROOT, TRADEAPP_DIR, ENV_FILE, LOG_DIR, REPORTS_DIR, RUN_NAME

Monitor background run:
  tail -f /opt/glebza/logs/backtest-<name>.log
  kill $(cat /opt/glebza/logs/backtest-<name>.pid)
EOF
}

log() {
  echo "==> $*"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --background)
        BACKGROUND=true
        shift
        ;;
      --name)
        RUN_NAME="${2:?--name requires a value}"
        shift 2
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      --)
        shift
        EXTRA_ARGS=("$@")
        return
        ;;
      *)
        EXTRA_ARGS=("$@")
        return
        ;;
    esac
  done
}

ensure_layout() {
  mkdir -p "${LOG_DIR}" "${REPORTS_DIR}" "${PYROOT}/glebza"
  if [[ ! -e "${PYROOT}/glebza/tradeapp" ]]; then
    ln -sfn "${TRADEAPP_DIR}" "${PYROOT}/glebza/tradeapp"
  fi
}

load_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "missing ${ENV_FILE}" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  export PYTHONPATH="${PYROOT}:${TRADEAPP_DIR}/src"
}

ensure_tradeapp_venv() {
  local python_bin="${TRADEAPP_DIR}/.venv/bin/python"
  if [[ ! -x "${python_bin}" ]]; then
    echo "missing ${python_bin} — create venv and install deps first:" >&2
    echo "  cd ${TRADEAPP_DIR}" >&2
    echo "  python3 -m venv .venv" >&2
    echo "  .venv/bin/pip install pandas numpy matplotlib psycopg2-binary certifi grpcio protobuf sentry-sdk \\" >&2
    echo "    --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple \\" >&2
    echo "    t-tech-investments>=0.3.5" >&2
    exit 1
  fi
}

default_backtest_args() {
  cat <<EOF
--interval
1d
--start-dt
2020-01-01T00:00:00+00:00
--end-dt
2026-01-01T00:00:00+00:00
--step
1y
--strategy-id
1
--plot-path
${REPORTS_DIR}/portfolio-backtest-${RUN_NAME}.png
EOF
}

run_backtest() {
  local python_bin="${TRADEAPP_DIR}/.venv/bin/python"
  local -a cmd=( "${python_bin}" -m framework.backtest )
  if [[ ${#EXTRA_ARGS[@]} -eq 0 ]]; then
    mapfile -t defaults < <(default_backtest_args)
    cmd+=( "${defaults[@]}" )
  else
    cmd+=( "${EXTRA_ARGS[@]}" )
  fi

  cd "${TRADEAPP_DIR}"
  if [[ "${BACKGROUND}" == true ]]; then
    local log_file="${LOG_DIR}/backtest-${RUN_NAME}.log"
    local pid_file="${LOG_DIR}/backtest-${RUN_NAME}.pid"
    log "background backtest -> ${log_file}"
    nohup "${cmd[@]}" >"${log_file}" 2>&1 &
    echo $! >"${pid_file}"
    log "pid=$(cat "${pid_file}")"
    log "tail -f ${log_file}"
  else
    log "foreground backtest in ${TRADEAPP_DIR}"
    exec "${cmd[@]}"
  fi
}

main() {
  parse_args "$@"
  ensure_layout
  load_env
  ensure_tradeapp_venv
  run_backtest
}

main "$@"
