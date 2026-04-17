#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PID_DIR="${ROOT_DIR}/.run"

stop_service() {
  local name="$1"
  local pid_file="${PID_DIR}/${name}.pid"

  if [[ ! -f "${pid_file}" ]]; then
    echo "${name} is not running."
    return
  fi

  local pgid
  pgid="$(cat "${pid_file}")"
  if kill -0 -- "-${pgid}" >/dev/null 2>&1; then
    kill -- "-${pgid}"
    echo "Stopped ${name} (process group ${pgid})"
  else
    echo "${name} PID file existed but process group ${pgid} was not running."
  fi

  rm -f "${pid_file}"
}

stop_service "tricys_goview"
stop_service "tricys_visual"
stop_service "tricys_hdf5"
stop_service "tricys_backend"