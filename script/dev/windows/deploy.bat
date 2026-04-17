@echo off
setlocal EnableDelayedExpansion

for %%I in ("%~dp0\..\..\..") do set ROOT_DIR=%%~fI
cd /d "%ROOT_DIR%"

call :print_header "Environment Check"
call :check_python
call :check_tool git git --version
call :check_tool node node --version
call :check_tool npm npm --version
call :check_tool docker docker --version
call :check_compose
call :check_tool omc omc --version

call :print_header "Deployment Modes"
echo 1. core-local      Install the Python core locally and register Modelica dependencies.
echo 2. fullstack-local Install dependencies and start backend, visual, goview, and hdf5 locally.
echo 3. docker-fullstack Build or pull containers and start the full stack with Docker Compose.
echo.

set /p DEPLOY_CHOICE=Choose deployment mode [1/2/3]: 
if "%DEPLOY_CHOICE%"=="1" goto :core_local
if /I "%DEPLOY_CHOICE%"=="core-local" goto :core_local
if "%DEPLOY_CHOICE%"=="2" goto :fullstack_local
if /I "%DEPLOY_CHOICE%"=="fullstack-local" goto :fullstack_local
if "%DEPLOY_CHOICE%"=="3" goto :docker_fullstack
if /I "%DEPLOY_CHOICE%"=="docker-fullstack" goto :docker_fullstack

echo Invalid choice. Enter 1, 2, 3, or the mode name.
exit /b 1

:core_local
call :require_tools python git omc
call :print_header "Deploy: core-local"
call :detect_core_local_status
call git submodule sync --recursive || exit /b 1
call git submodule update --init --recursive || exit /b 1

set VENV_DIR=%ROOT_DIR%\.venv
if not exist "%VENV_DIR%\Scripts\python.exe" (
  call %PYTHON_LAUNCHER% -m venv "%VENV_DIR%" || exit /b 1
)

call "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip || exit /b 1
call "%VENV_DIR%\Scripts\python.exe" -m pip install -e . || exit /b 1
call omc "%ROOT_DIR%\script\modelica_install\install.mos" || exit /b 1

call :print_header "Next Suggestions"
echo 1. Activate the environment: .\.venv\Scripts\activate
echo 2. Run tricys example to verify the core workflow.
echo 3. If Modelica import fails, verify that omc is still in PATH and rerun this script.
exit /b 0

:fullstack_local
call :require_tools python git node npm
call :print_header "Deploy: fullstack-local"
call :detect_fullstack_local_status
if not "%FULLSTACK_STATUS%"=="stopped" (
  call :confirm_fullstack_local_action
  if /I "%FULLSTACK_ACTION%"=="skip" (
    call :print_fullstack_next_steps
    exit /b 0
  )
  if /I "%FULLSTACK_ACTION%"=="restart" (
    call "%ROOT_DIR%\script\dev\windows\stop_all.bat" || exit /b 1
  )
)
call "%ROOT_DIR%\script\dev\windows\install_all_deps.bat" || exit /b 1
call "%ROOT_DIR%\script\dev\windows\start_all.bat" || exit /b 1

call :print_fullstack_next_steps
exit /b 0

:docker_fullstack
call :require_tools docker compose
call :print_header "Deploy: docker-fullstack"
call :detect_docker_fullstack_status
if "%HAS_DOCKER_COMPOSE_PLUGIN%"=="1" (
  call docker compose up -d --build || exit /b 1
) else (
  call docker-compose up -d --build || exit /b 1
)

call :print_header "Next Suggestions"
echo 1. Check container status with docker compose ps.
echo 2. Open the services in your browser.
echo    Backend: http://localhost:8000
echo    HDF5:    http://localhost:8050/hdf5/
echo    Visual:  http://localhost:8080
echo    GoView:  http://localhost:3020
echo 3. View logs with docker compose logs -f and stop the stack with docker compose down.
exit /b 0

:check_tool
set TOOL_NAME=%~1
set TOOL_CMD=%~2
set TOOL_ARG=%~3

where %TOOL_CMD% >nul 2>nul
if errorlevel 1 (
  echo [MISSING] %TOOL_NAME%
  set HAS_%TOOL_NAME%=0
  exit /b 0
)

call %TOOL_CMD% %TOOL_ARG% >nul 2>nul
if errorlevel 1 (
  echo [MISSING] %TOOL_NAME%
  set HAS_%TOOL_NAME%=0
  exit /b 0
)

for /f "delims=" %%V in ('call %TOOL_CMD% %TOOL_ARG% 2^>^&1') do (
  echo [OK     ] %TOOL_NAME% %%V
  goto :check_tool_done
)
:check_tool_done
set HAS_%TOOL_NAME%=1
exit /b 0

:check_compose
docker compose version >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%V in ('docker compose version 2^>^&1') do (
    echo [OK     ] compose %%V
    goto :compose_plugin_done
  )
:compose_plugin_done
  set HAS_compose=1
  set HAS_DOCKER_COMPOSE_PLUGIN=1
  exit /b 0
)

where docker-compose >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%V in ('docker-compose --version 2^>^&1') do (
    echo [OK     ] compose %%V
    goto :compose_standalone_done
  )
:compose_standalone_done
  set HAS_compose=1
  set HAS_DOCKER_COMPOSE_PLUGIN=0
  exit /b 0
)

echo [MISSING] compose
set HAS_compose=0
set HAS_DOCKER_COMPOSE_PLUGIN=0
exit /b 0

:require_tools
set MISSING_LIST=
set REQUIREMENT_ARGS=%*
:require_loop
if "%~1"=="" goto :require_done
if not "!HAS_%~1!"=="1" set MISSING_LIST=!MISSING_LIST! %~1
shift
goto :require_loop

:require_done
if defined MISSING_LIST (
  call :print_header "Missing Requirements"
  echo Missing tools:!MISSING_LIST!
  for %%T in (!REQUIREMENT_ARGS!) do call :print_tool_recommendation %%T
  echo Install the missing dependencies and ensure they are available in PATH, then rerun this script.
  exit /b 1
)
exit /b 0

:print_tool_recommendation
if "!HAS_%~1!"=="1" exit /b 0

if /I "%~1"=="python" (
  echo - python: recommended Python 3.10+ ^(minimum supported: 3.8^)
  exit /b 0
)

if /I "%~1"=="git" (
  echo - git: recommended Git 2.40+
  exit /b 0
)

if /I "%~1"=="node" (
  echo - node: recommended Node.js 20 LTS+ ^(minimum used in submodule constraints: 16.14^)
  exit /b 0
)

if /I "%~1"=="npm" (
  echo - npm: recommended npm 10+
  exit /b 0
)

if /I "%~1"=="docker" (
  echo - docker: recommended Docker 27+
  exit /b 0
)

if /I "%~1"=="compose" (
  echo - compose: recommended Docker Compose v2+
  exit /b 0
)

if /I "%~1"=="omc" (
  echo - omc: recommended OpenModelica 1.24+
  exit /b 0
)

echo - %~1: install a recent stable version and ensure it is available in PATH.
exit /b 0

:print_header
echo.
echo ========================================================================
echo %~1
echo ========================================================================
exit /b 0

:check_python
where py >nul 2>nul
if not errorlevel 1 (
  py --version >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%V in ('py --version 2^>^&1') do (
      echo [OK     ] python %%V
      set HAS_python=1
      set PYTHON_LAUNCHER=py
      exit /b 0
    )
  )
)

where python >nul 2>nul
if not errorlevel 1 (
  python --version >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%V in ('python --version 2^>^&1') do (
      echo [OK     ] python %%V
      set HAS_python=1
      set PYTHON_LAUNCHER=python
      exit /b 0
    )
  )
)

echo [MISSING] python
set HAS_python=0
set PYTHON_LAUNCHER=
exit /b 0

:detect_core_local_status
set CORE_STATUS=fresh
set VENV_DIR=%ROOT_DIR%\.venv
if exist "%ROOT_DIR%\venv\Scripts\python.exe" set VENV_DIR=%ROOT_DIR%\venv

if exist "%VENV_DIR%\Scripts\python.exe" (
  call "%VENV_DIR%\Scripts\python.exe" -c "import tricys" >nul 2>nul
  if not errorlevel 1 (
    set CORE_STATUS=installed
  ) else (
    set CORE_STATUS=venv-only
  )
)

if "%CORE_STATUS%"=="installed" (
  echo Detected an existing local core environment. The deployment will perform an incremental refresh.
) else if "%CORE_STATUS%"=="venv-only" (
  echo Detected an existing virtual environment, but tricys is not importable yet. The deployment will complete the installation.
) else (
  echo No local core environment detected. A fresh local core deployment will be created.
)
exit /b 0

:detect_fullstack_local_status
set RUNNING_COUNT=0
set FULLSTACK_STATUS=stopped
call :check_local_service tricys_backend 8000
call :check_local_service tricys_goview 3020
call :check_local_service tricys_visual 5173
call :check_local_service tricys_hdf5 8050

if "%RUNNING_COUNT%"=="4" (
  set FULLSTACK_STATUS=running
  echo Detected that the local full stack is already running.
) else if "%RUNNING_COUNT%"=="0" (
  set FULLSTACK_STATUS=stopped
  echo No running local full stack detected. The deployment will perform a normal local startup.
) else (
  set FULLSTACK_STATUS=partial
  echo Detected a partial local stack state.
)
exit /b 0

:confirm_fullstack_local_action
set FULLSTACK_ACTION=
:confirm_fullstack_local_action_loop
if /I "%FULLSTACK_STATUS%"=="running" (
  set /p FULLSTACK_CHOICE=Local full stack is already running. Choose [s]kip, [r]estart, or [c]ontinue: 
) else (
  set /p FULLSTACK_CHOICE=Local full stack is partially running. Choose [s]kip, [r]estart, or [c]ontinue: 
)

if /I "%FULLSTACK_CHOICE%"=="s" set FULLSTACK_ACTION=skip
if /I "%FULLSTACK_CHOICE%"=="skip" set FULLSTACK_ACTION=skip
if /I "%FULLSTACK_CHOICE%"=="r" set FULLSTACK_ACTION=restart
if /I "%FULLSTACK_CHOICE%"=="restart" set FULLSTACK_ACTION=restart
if /I "%FULLSTACK_CHOICE%"=="c" set FULLSTACK_ACTION=continue
if /I "%FULLSTACK_CHOICE%"=="continue" set FULLSTACK_ACTION=continue

if not defined FULLSTACK_ACTION (
  echo Invalid choice. Enter s, r, c, skip, restart, or continue.
  goto :confirm_fullstack_local_action_loop
)

if /I "%FULLSTACK_ACTION%"=="continue" (
  echo Continuing without stopping existing services.
) else if /I "%FULLSTACK_ACTION%"=="restart" (
  echo Stopping the existing local full stack before redeploying.
) else (
  echo Skipping fullstack deployment because services are already present.
)
exit /b 0

:print_fullstack_next_steps
call :print_header "Next Suggestions"
echo 1. Open the services in your browser after startup settles.
echo    Backend: http://localhost:8000
echo    HDF5:    http://localhost:8050/hdf5/
echo    Visual:  http://localhost:5173
echo    GoView:  http://localhost:3020
echo 2. Stop the local stack with Makefile.bat app-stop.
echo 3. If a port is occupied, stop the conflicting process or any existing Docker stack first.
exit /b 0

:check_local_service
set SERVICE_NAME=%~1
set SERVICE_PORT=%~2
set PID_FILE=%ROOT_DIR%\.run\%SERVICE_NAME%.pid

if exist "%PID_FILE%" (
  set /p SERVICE_PID=<"%PID_FILE%"
  tasklist /FI "PID eq %SERVICE_PID%" | find "%SERVICE_PID%" >nul
  if not errorlevel 1 (
    set /a RUNNING_COUNT+=1
    exit /b 0
  )
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%SERVICE_PORT% .*LISTENING"') do (
  set /a RUNNING_COUNT+=1
  exit /b 0
)

exit /b 0

:detect_docker_fullstack_status
set DOCKER_SERVICE_COUNT=0
set DOCKER_HEALTHY_COUNT=0

if "%HAS_DOCKER_COMPOSE_PLUGIN%"=="1" (
  for /f "delims=" %%L in ('docker compose ps --format "{{.Service}}|{{.State}}|{{.Health}}" 2^>nul') do call :process_compose_line "%%L"
) else (
  for /f "delims=" %%L in ('docker-compose ps --format "{{.Service}}|{{.State}}|{{.Health}}" 2^>nul') do call :process_compose_line "%%L"
)

if "%DOCKER_SERVICE_COUNT%"=="0" (
  echo No existing Docker stack detected. The deployment will create or start the compose stack.
) else if "%DOCKER_HEALTHY_COUNT%"=="4" (
  echo Detected an existing healthy Docker stack. The deployment will refresh it with compose up.
) else (
  echo Detected an existing but incomplete Docker stack state. The deployment will attempt to reconcile it with compose up.
)
exit /b 0

:process_compose_line
set COMPOSE_LINE=%~1
for /f "tokens=1,2,3 delims=|" %%A in ("%COMPOSE_LINE%") do (
  if /I "%%A"=="tricys-backend" call :record_compose_state "%%B" "%%C"
  if /I "%%A"=="tricys-visual" call :record_compose_state "%%B" "%%C"
  if /I "%%A"=="tricys-goview" call :record_compose_state "%%B" "%%C"
  if /I "%%A"=="tricys-hdf5" call :record_compose_state "%%B" "%%C"
)
exit /b 0

:record_compose_state
set /a DOCKER_SERVICE_COUNT+=1
if /I "%~1"=="running" (
  if /I "%~2"=="healthy" set /a DOCKER_HEALTHY_COUNT+=1
)
exit /b 0