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

ensure_owned_file_parent() {
  local file_path="$1"

  if [[ -z "${file_path}" ]]; then
    return
  fi

  mkdir -p "$(dirname "${file_path}")"
  touch "${file_path}"
  chown "${APP_USER}:${APP_GROUP}" "${file_path}"
  chown -R "${APP_USER}:${APP_GROUP}" "$(dirname "${file_path}")"
}

sqlite_file_path=""
database_url="${DATABASE_URL:-}"

case "${database_url}" in
  sqlite:////*)
    sqlite_file_path="/${database_url#sqlite:////}"
    ;;
  sqlite:///*)
    sqlite_file_path="${database_url#sqlite://}"
    ;;
esac

ensure_owned_dir "${WORKSPACES_DIR:-}"
ensure_owned_dir "${ASSETS_DIR:-}"
ensure_owned_file_parent "${sqlite_file_path}"

exec sudo -E -H -u "${APP_USER}" env PATH="/home/appuser/.local/bin:${PATH}" "$@"