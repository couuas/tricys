@echo off
setlocal

REM Root directory of this script
set ROOT_DIR=%~dp0

REM --- Init/Update submodules ---
cd /d "%ROOT_DIR%"
call git submodule update --init --recursive

REM --- Python venv setup for tricys + backend ---
set VENV_ACTIVATE=%ROOT_DIR%venv\Scripts\activate.bat
if not exist "%VENV_ACTIVATE%" (
  py -m venv venv
)
call "%VENV_ACTIVATE%"

REM Install tricys (root) deps
call pip install -e ".[dev,docs]"

REM Install backend deps if requirements.txt exists
if exist "%ROOT_DIR%tricys_backend\requirements.txt" (
  call pip install -r "%ROOT_DIR%tricys_backend\requirements.txt"
)

REM --- Frontend deps ---
if exist "%ROOT_DIR%tricys_visual\package.json" (
  cd /d "%ROOT_DIR%tricys_visual"
  call npm.cmd install
)

REM --- GoView deps ---
if exist "%ROOT_DIR%tricys_goview\package.json" (
  cd /d "%ROOT_DIR%tricys_goview"
  call npm.cmd install
)

cd /d "%ROOT_DIR%"
endlocal
