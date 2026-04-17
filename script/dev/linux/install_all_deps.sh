#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TRICYS_GOVIEW_BRANCH="main"

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi

  echo "Python is required but was not found in PATH." >&2
  exit 1
}

PYTHON_BIN="$(find_python)"

if [[ -d "${ROOT_DIR}/.venv" ]]; then
  VENV_DIR="${ROOT_DIR}/.venv"
elif [[ -d "${ROOT_DIR}/venv" ]]; then
  VENV_DIR="${ROOT_DIR}/venv"
else
  VENV_DIR="${ROOT_DIR}/.venv"
fi

cd "${ROOT_DIR}"

git submodule sync --recursive
git submodule update --init --recursive

if [[ -d "${ROOT_DIR}/tricys_goview" ]]; then
  git -C "${ROOT_DIR}/tricys_goview" fetch origin "${TRICYS_GOVIEW_BRANCH}"
  if git -C "${ROOT_DIR}/tricys_goview" rev-parse --verify "${TRICYS_GOVIEW_BRANCH}" >/dev/null 2>&1; then
    git -C "${ROOT_DIR}/tricys_goview" checkout "${TRICYS_GOVIEW_BRANCH}"
  else
    git -C "${ROOT_DIR}/tricys_goview" checkout -b "${TRICYS_GOVIEW_BRANCH}" --track "origin/${TRICYS_GOVIEW_BRANCH}"
  fi
  git -C "${ROOT_DIR}/tricys_goview" pull --ff-only origin "${TRICYS_GOVIEW_BRANCH}"
fi

if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
pip install -e ".[dev,docs]"

if [[ -f "${ROOT_DIR}/tricys_backend/requirements.txt" ]]; then
  pip install -r "${ROOT_DIR}/tricys_backend/requirements.txt"
fi

if [[ -f "${ROOT_DIR}/tricys_visual/package.json" ]]; then
  cd "${ROOT_DIR}/tricys_visual"
  npm install
fi

if [[ -f "${ROOT_DIR}/tricys_goview/package.json" ]]; then
  cd "${ROOT_DIR}/tricys_goview"
  npm install
fi

cd "${ROOT_DIR}"

echo "Dependencies installed successfully."
echo "Python virtual environment: ${VENV_DIR}"