#!/usr/bin/env bash

set -euo pipefail

APP_USER="appuser"
APP_GROUP="appuser"
WEB_ROOT="/usr/share/nginx/html"
WEB_BUNDLE_ROOT="/opt/tricys-web"
NGINX_CONFIG_ROOT="/etc/nginx/tricys"

ensure_owned_dir() {
  local dir_path="$1"

  if [[ -z "${dir_path}" ]]; then
    return
  fi

  mkdir -p "${dir_path}"
  chown -R "${APP_USER}:${APP_GROUP}" "${dir_path}"
}

run_as_appuser() {
  exec sudo -E -H -u "${APP_USER}" env PATH="/home/appuser/.local/bin:${PATH}" "$@"
}

start_nginx_app() {
  local app_name="$1"
  local source_dir="${WEB_BUNDLE_ROOT}/${app_name}"
  local source_conf="${NGINX_CONFIG_ROOT}/${app_name}.conf"

  rm -f /etc/nginx/conf.d/default.conf
  rm -f /etc/nginx/sites-enabled/default
  rm -f /etc/nginx/sites-available/default
  cp "${source_conf}" /etc/nginx/conf.d/default.conf

  mkdir -p "${WEB_ROOT}"
  find "${WEB_ROOT}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cp -a "${source_dir}/." "${WEB_ROOT}/"

  exec nginx -g 'daemon off;'
}

mode="${1:-backend}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "${mode}" in
  backend)
    if [[ $# -eq 0 ]]; then
      set -- uvicorn tricys_backend.main:app --host 0.0.0.0 --port 8000
    fi
    exec /usr/local/bin/tricys_backend_entrypoint.sh "$@"
    ;;
  hdf5)
    if [[ $# -eq 0 ]]; then
      ensure_owned_dir "${HDF5_CONTEXTS_DIR:-/data/hdf5_contexts}"
      set -- \
        tricys hdf5 --server-mode --host 0.0.0.0 --port 8050 \
        --base-pathname "${HDF5_VISUALIZER_BASE_URL:-/hdf5/}" \
        --secret "${HDF5_VISUALIZER_SECRET:-change-me-before-production}" \
        --context-dir "${HDF5_CONTEXTS_DIR:-/data/hdf5_contexts}" \
        --no-browser
    else
      ensure_owned_dir "${HDF5_CONTEXTS_DIR:-/data/hdf5_contexts}"
    fi
    run_as_appuser "$@"
    ;;
  visual)
    start_nginx_app visual
    ;;
  goview)
    start_nginx_app goview
    ;;
  *)
    exec "${mode}" "$@"
    ;;
esac