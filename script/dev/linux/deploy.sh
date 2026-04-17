#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
HAS_DOCKER_COMPOSE_PLUGIN=0
PYTHON_LAUNCHER=""

print_header() {
  printf '\n========================================================================\n%s\n========================================================================\n' "$1"
}

check_tool() {
  local name="$1"
  local command_name="$2"
  shift 2

  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf '[MISSING] %s\n' "$name"
    eval "HAS_${name}=0"
    return 0
  fi

  local version
  version="$($command_name "$@" 2>&1 | head -n 1)"
  printf '[OK     ] %s %s\n' "$name" "$version"
  eval "HAS_${name}=1"
}

check_compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    printf '[OK     ] compose %s\n' "$(docker compose version | head -n 1)"
    HAS_compose=1
    HAS_DOCKER_COMPOSE_PLUGIN=1
    return 0
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    printf '[OK     ] compose %s\n' "$(docker-compose --version | head -n 1)"
    HAS_compose=1
    return 0
  fi

  printf '[MISSING] compose\n'
  HAS_compose=0
}

require_tools() {
  local missing=()
  local tool
  for tool in "$@"; do
    if [[ "${!tool:-0}" != "1" ]]; then
      missing+=("$tool")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    print_header "Missing Requirements"
    printf 'Missing tools: %s\n' "${missing[*]}"
    for tool in "${missing[@]}"; do
      print_tool_recommendation "$tool"
    done
    printf 'Install the missing dependencies and ensure they are available in PATH, then rerun this script.\n'
    exit 1
  fi
}

print_tool_recommendation() {
  case "$1" in
    python)
      printf '%s\n' '- python: recommended Python 3.10+ (minimum supported: 3.8)'
      ;;
    git)
      printf '%s\n' '- git: recommended Git 2.40+'
      ;;
    node)
      printf '%s\n' '- node: recommended Node.js 20 LTS+ (minimum used in submodule constraints: 16.14)'
      ;;
    npm)
      printf '%s\n' '- npm: recommended npm 10+'
      ;;
    docker)
      printf '%s\n' '- docker: recommended Docker 27+'
      ;;
    compose)
      printf '%s\n' '- compose: recommended Docker Compose v2+'
      ;;
    omc)
      printf '%s\n' '- omc: recommended OpenModelica 1.24+'
      ;;
    *)
      printf '%s\n' "- $1: install a recent stable version and ensure it is available in PATH."
      ;;
  esac
}

deploy_core_local() {
  require_tools python git omc
  print_header "Deploy: core-local"
  detect_core_local_status
  cd "$ROOT_DIR"
  git submodule sync --recursive
  git submodule update --init --recursive

  local venv_dir="$ROOT_DIR/.venv"
  if [[ ! -x "$venv_dir/bin/python" ]]; then
    "$PYTHON_LAUNCHER" -m venv "$venv_dir"
  fi

  "$venv_dir/bin/python" -m pip install --upgrade pip
  "$venv_dir/bin/python" -m pip install -e .
  omc "$ROOT_DIR/script/modelica_install/install.mos"

  print_header "Next Suggestions"
  printf '1. Activate the environment: source .venv/bin/activate\n'
  printf '2. Run tricys example to verify the core workflow.\n'
  printf '3. If Modelica import fails, verify that omc is still in PATH and rerun this script.\n'
}

deploy_fullstack_local() {
  require_tools python git node npm
  print_header "Deploy: fullstack-local"
  detect_fullstack_local_status
  if [[ "$FULLSTACK_STATUS" != "stopped" ]]; then
    confirm_fullstack_local_action
    case "$FULLSTACK_ACTION" in
      skip)
        print_fullstack_next_steps
        return
        ;;
      restart)
        bash "$ROOT_DIR/script/dev/linux/stop_all.sh"
        ;;
    esac
  fi
  bash "$ROOT_DIR/script/dev/linux/install_all_deps.sh"
  bash "$ROOT_DIR/script/dev/linux/start_all.sh"

  print_fullstack_next_steps
}

deploy_docker_fullstack() {
  require_tools docker compose
  print_header "Deploy: docker-fullstack"
  detect_docker_fullstack_status
  cd "$ROOT_DIR"

  if [[ "$HAS_DOCKER_COMPOSE_PLUGIN" == "1" ]]; then
    docker compose up -d --build
  else
    docker-compose up -d --build
  fi

  print_header "Next Suggestions"
  printf '1. Check container status with docker compose ps.\n'
  printf '2. Open the services in your browser.\n'
  printf '   Backend: http://localhost:8000\n'
  printf '   HDF5:    http://localhost:8050/hdf5/\n'
  printf '   Visual:  http://localhost:8080\n'
  printf '   GoView:  http://localhost:3020\n'
  printf '3. View logs with docker compose logs -f and stop the stack with docker compose down.\n'
}

detect_core_local_status() {
  local venv_dir="$ROOT_DIR/.venv"
  if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
    venv_dir="$ROOT_DIR/venv"
  fi

  if [[ -x "$venv_dir/bin/python" ]]; then
    if "$venv_dir/bin/python" -c 'import tricys' >/dev/null 2>&1; then
      printf 'Detected an existing local core environment. The deployment will perform an incremental refresh.\n'
      return
    fi
    printf 'Detected an existing virtual environment, but tricys is not importable yet. The deployment will complete the installation.\n'
    return
  fi

  printf 'No local core environment detected. A fresh local core deployment will be created.\n'
}

detect_fullstack_local_status() {
  local running_count=0
  FULLSTACK_STATUS="stopped"
  check_local_service tricys_backend 8000 && ((running_count+=1))
  check_local_service tricys_goview 3020 && ((running_count+=1))
  check_local_service tricys_visual 5173 && ((running_count+=1))
  check_local_service tricys_hdf5 8050 && ((running_count+=1))

  if [[ "$running_count" -eq 4 ]]; then
    FULLSTACK_STATUS="running"
    printf 'Detected that the local full stack is already running.\n'
  elif [[ "$running_count" -eq 0 ]]; then
    FULLSTACK_STATUS="stopped"
    printf 'No running local full stack detected. The deployment will perform a normal local startup.\n'
  else
    FULLSTACK_STATUS="partial"
    printf 'Detected a partial local stack state.\n'
  fi
}

confirm_fullstack_local_action() {
  while true; do
    if [[ "$FULLSTACK_STATUS" == "running" ]]; then
      read -r -p 'Local full stack is already running. Choose [s]kip, [r]estart, or [c]ontinue: ' FULLSTACK_CHOICE
    else
      read -r -p 'Local full stack is partially running. Choose [s]kip, [r]estart, or [c]ontinue: ' FULLSTACK_CHOICE
    fi

    case "$FULLSTACK_CHOICE" in
      s|S|skip|SKIP|Skip)
        FULLSTACK_ACTION="skip"
        printf 'Skipping fullstack deployment because services are already present.\n'
        return
        ;;
      r|R|restart|RESTART|Restart)
        FULLSTACK_ACTION="restart"
        printf 'Stopping the existing local full stack before redeploying.\n'
        return
        ;;
      c|C|continue|CONTINUE|Continue)
        FULLSTACK_ACTION="continue"
        printf 'Continuing without stopping existing services.\n'
        return
        ;;
      *)
        printf 'Invalid choice. Enter s, r, c, skip, restart, or continue.\n'
        ;;
    esac
  done
}

print_fullstack_next_steps() {
  print_header "Next Suggestions"
  printf '1. Open the services in your browser after startup settles.\n'
  printf '   Backend: http://localhost:8000\n'
  printf '   HDF5:    http://localhost:8050/hdf5/\n'
  printf '   Visual:  http://localhost:5173\n'
  printf '   GoView:  http://localhost:3020\n'
  printf '2. Stop the local stack with make app-stop.\n'
  printf '3. If a port is occupied, stop the conflicting process or any existing Docker stack first.\n'
}

check_local_service() {
  local service_name="$1"
  local service_port="$2"
  local pid_file="$ROOT_DIR/.run/${service_name}.pid"

  if [[ -f "$pid_file" ]]; then
    local service_pid
    service_pid="$(cat "$pid_file")"
    if kill -0 -- "-${service_pid}" >/dev/null 2>&1 || kill -0 "$service_pid" >/dev/null 2>&1; then
      return 0
    fi
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :${service_port}" | tail -n +2 | grep -q .
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${service_port}" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi

  return 1
}

detect_docker_fullstack_status() {
  local service_count=0
  local healthy_count=0
  local compose_output

  if [[ "$HAS_DOCKER_COMPOSE_PLUGIN" == "1" ]]; then
    compose_output="$(docker compose ps --format '{{.Service}}|{{.State}}|{{.Health}}' 2>/dev/null || true)"
  else
    compose_output="$(docker-compose ps --format '{{.Service}}|{{.State}}|{{.Health}}' 2>/dev/null || true)"
  fi

  while IFS='|' read -r service state health; do
    case "$service" in
      tricys-backend|tricys-visual|tricys-goview|tricys-hdf5)
        ((service_count+=1))
        if [[ "$state" == "running" && "$health" == "healthy" ]]; then
          ((healthy_count+=1))
        fi
        ;;
    esac
  done <<< "$compose_output"

  if [[ "$service_count" -eq 0 ]]; then
    printf 'No existing Docker stack detected. The deployment will create or start the compose stack.\n'
  elif [[ "$healthy_count" -eq 4 ]]; then
    printf 'Detected an existing healthy Docker stack. The deployment will refresh it with compose up.\n'
  else
    printf 'Detected an existing but incomplete Docker stack state. The deployment will attempt to reconcile it with compose up.\n'
  fi
}

main() {
  print_header "Environment Check"
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_LAUNCHER="python3"
    check_tool python python3 --version || true
  elif command -v python >/dev/null 2>&1; then
    PYTHON_LAUNCHER="python"
    check_tool python python --version || true
  else
    printf '[MISSING] python\n'
    HAS_python=0
  fi
  check_tool git git --version || true
  check_tool node node --version || true
  check_tool npm npm --version || true
  check_tool docker docker --version || true
  check_compose || true
  check_tool omc omc --version || true

  print_header "Deployment Modes"
  printf '1. core-local      Install the Python core locally and register Modelica dependencies.\n'
  printf '2. fullstack-local Install dependencies and start backend, visual, goview, and hdf5 locally.\n'
  printf '3. docker-fullstack Build or pull containers and start the full stack with Docker Compose.\n\n'

  read -r -p 'Choose deployment mode [1/2/3]: ' deploy_choice
  case "$deploy_choice" in
    1|core-local)
      deploy_core_local
      ;;
    2|fullstack-local)
      deploy_fullstack_local
      ;;
    3|docker-fullstack)
      deploy_docker_fullstack
      ;;
    *)
      printf 'Invalid choice. Enter 1, 2, 3, or the mode name.\n' >&2
      exit 1
      ;;
  esac
}

main "$@"