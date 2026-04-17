#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PID_DIR="${ROOT_DIR}/.run"
LOG_DIR="${ROOT_DIR}/log/dev"

mkdir -p "${PID_DIR}" "${LOG_DIR}"

if [[ -f "${ROOT_DIR}/.venv/bin/activate" ]]; then
  VENV_DIR="${ROOT_DIR}/.venv"
elif [[ -f "${ROOT_DIR}/venv/bin/activate" ]]; then
  VENV_DIR="${ROOT_DIR}/venv"
else
  echo "No Python virtual environment found. Run script/dev/linux/install_all_deps.sh first." >&2
  exit 1
fi

check_port() {
  local port="$1"
  local service_name="$2"

  if command -v ss >/dev/null 2>&1; then
    if ss -ltn "sport = :${port}" | tail -n +2 | grep -q .; then
      echo "Error: port ${port} is already in use, so ${service_name} cannot start." >&2
      echo "Hint: if you previously started the Docker stack, run 'docker compose down' first." >&2
      echo "Hint: if you previously started the local app stack, run 'make app-stop' first." >&2
      exit 1
    fi
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    if lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "Error: port ${port} is already in use, so ${service_name} cannot start." >&2
      echo "Hint: if you previously started the Docker stack, run 'docker compose down' first." >&2
      echo "Hint: if you previously started the local app stack, run 'make app-stop' first." >&2
      exit 1
    fi
  fi
}

check_port 8000 tricys_backend
check_port 3020 tricys_goview
check_port 8050 tricys_hdf5

HDF5_SECRET="${HDF5_VISUALIZER_SECRET:-your-super-secret-key-change-in-production}"
HDF5_CONTEXTS_DIR="${HDF5_CONTEXTS_DIR:-${ROOT_DIR}/tricys_backend/hdf5_contexts}"

mkdir -p "${HDF5_CONTEXTS_DIR}"

start_service() {
  local name="$1"
  local workdir="$2"
  local command="$3"
  local pid_file="${PID_DIR}/${name}.pid"
  local log_file="${LOG_DIR}/${name}.log"

  if [[ -f "${pid_file}" ]]; then
    local existing_pid
    existing_pid="$(cat "${pid_file}")"
    if kill -0 "${existing_pid}" >/dev/null 2>&1; then
      echo "${name} is already running with PID ${existing_pid}."
      return
    fi
    rm -f "${pid_file}"
  fi

  nohup bash -lc "cd '${workdir}' && ${command}" >"${log_file}" 2>&1 &
  local pid=$!
  echo "${pid}" >"${pid_file}"
  echo "Started ${name} (PID ${pid})"
}

start_service \
  "tricys_backend" \
  "${ROOT_DIR}" \
  "source '${VENV_DIR}/bin/activate' && python -m uvicorn tricys_backend.main:app --host 0.0.0.0 --port 8000 --reload"

start_service \
  "tricys_hdf5" \
  "${ROOT_DIR}" \
  "source '${VENV_DIR}/bin/activate' && tricys hdf5 --server-mode --host 0.0.0.0 --port 8050 --base-pathname /hdf5/ --secret '${HDF5_SECRET}' --context-dir '${HDF5_CONTEXTS_DIR}' --no-browser"

start_service \
  "tricys_visual" \
  "${ROOT_DIR}/tricys_visual" \
  "npm run dev -- --host 0.0.0.0"

start_service \
  "tricys_goview" \
  "${ROOT_DIR}/tricys_goview" \
  "npm run dev -- --host 0.0.0.0"

echo
echo "Services are starting in the background."
echo "Backend: http://localhost:8000"
echo "HDF5:    http://localhost:8050/hdf5/"
echo "Visual:  http://localhost:5173"
echo "GoView:  http://localhost:3020"
echo "Logs:    ${LOG_DIR}"
echo "Stop:    make app-stop"