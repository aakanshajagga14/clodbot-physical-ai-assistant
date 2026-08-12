#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_ENV="${PROJECT_DIR}/.venv-cyberwave"
if [[ ! -x "${PYTHON_ENV}/bin/python" ]]; then
  PYTHON_ENV="${PROJECT_DIR}/.venv"
fi
PYTHON_BIN="${PYTHON_ENV}/bin/python"
UVICORN_BIN="${PYTHON_ENV}/bin/uvicorn"
NODE_BIN="/Users/aakanshajagga/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"

if [[ ! -x "${PYTHON_BIN}" || ! -x "${UVICORN_BIN}" ]]; then
  echo "Clodbot environment is missing. Create a Python 3.10+ environment and install the dashboard dependencies."
  exit 1
fi

if [[ ! -x "${NODE_BIN}" ]]; then
  NODE_BIN="$(command -v node || true)"
fi
if [[ -z "${NODE_BIN}" || ! -x "${NODE_BIN}" ]]; then
  echo "Node.js 22+ is required for the dashboard."
  exit 1
fi

if [[ -f "${PROJECT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.env"
  set +a
fi

export CLODBOT_MODE="${CLODBOT_MODE:-simulation}"
export CLODBOT_CYBERWAVE_MOCK="${CLODBOT_CYBERWAVE_MOCK:-true}"

cleanup() {
  kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "${PROJECT_DIR}"
"${UVICORN_BIN}" clodbot.api.server:app --host 127.0.0.1 --port 8000 &
API_PID=$!

cd "${PROJECT_DIR}/frontend"
"${NODE_BIN}" ./node_modules/vinext/dist/cli.js dev &
WEB_PID=$!

echo ""
echo "CLODBOT // INDUSTRIAL SAFETY COPILOT"
echo "Dashboard: http://localhost:3000"
echo "State API: http://localhost:8000/api/state"
echo "Cyberwave: ${CLODBOT_CYBERWAVE_MOCK} (mock is always labeled in the UI)"
echo "Press Ctrl+C to stop both services."
echo ""

wait "${API_PID}" "${WEB_PID}"
