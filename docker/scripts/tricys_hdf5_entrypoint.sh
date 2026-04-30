#!/usr/bin/env bash

set -euo pipefail

APP_USER="appuser"
APP_GROUP="appuser"

ensure_owned_dir() {
  local dir_path="$1"

  if [[ -z "${dir_path}" ]]; then
    return
  fi

  mkdir -p "${dir_path}"
  chown -R "${APP_USER}:${APP_GROUP}" "${dir_path}"
}

run_as_appuser() {
  exec sudo -E -H -u "${APP_USER}" env PATH="/home/appuser/.local/bin:${PATH}" PYTHONPATH="${PYTHONPATH:-/opt/tricys-src}" "$@"
}

context_dir="${HDF5_CONTEXTS_DIR:-/data/hdf5_contexts}"
port="${HDF5_VISUALIZER_PORT:-8050}"
base_url="${HDF5_VISUALIZER_BASE_URL:-/hdf5/}"
secret="${HDF5_VISUALIZER_SECRET:-change-me-before-production}"

ensure_owned_dir "${context_dir}"

if [[ $# -eq 0 ]]; then
  set -- \
    python3 -m tricys.visualizer.main --server-mode --host 0.0.0.0 --port "${port}" \
    --base-pathname "${base_url}" \
    --secret "${secret}" \
    --context-dir "${context_dir}" \
    --no-browser
fi

run_as_appuser "$@"