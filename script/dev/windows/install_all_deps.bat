@echo off
setlocal EnableDelayedExpansion

for %%I in ("%~dp0\..\..\..") do set ROOT_DIR=%%~fI
set TRICYS_GOVIEW_BRANCH=main

cd /d "%ROOT_DIR%"
call git submodule sync --recursive
call git submodule update --init --recursive

if exist "%ROOT_DIR%\tricys_goview" (
  call git -C "%ROOT_DIR%\tricys_goview" fetch origin %TRICYS_GOVIEW_BRANCH%
  call git -C "%ROOT_DIR%\tricys_goview" rev-parse --verify %TRICYS_GOVIEW_BRANCH% >nul 2>nul
  if errorlevel 1 (
    call git -C "%ROOT_DIR%\tricys_goview" checkout -b %TRICYS_GOVIEW_BRANCH% --track origin/%TRICYS_GOVIEW_BRANCH%
  ) else (
    call git -C "%ROOT_DIR%\tricys_goview" checkout %TRICYS_GOVIEW_BRANCH%
  )
  call git -C "%ROOT_DIR%\tricys_goview" pull --ff-only origin %TRICYS_GOVIEW_BRANCH%
)

set VENV_DIR=%ROOT_DIR%\.venv
if exist "%ROOT_DIR%\venv\Scripts\activate.bat" set VENV_DIR=%ROOT_DIR%\venv

if not exist "%VENV_DIR%\Scripts\activate.bat" (
  py -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

call pip install -e ".[dev,docs]"

if exist "%ROOT_DIR%\tricys_backend\requirements.txt" (
  call pip install -r "%ROOT_DIR%\tricys_backend\requirements.txt"
)

if exist "%ROOT_DIR%\tricys_visual\package.json" (
  cd /d "%ROOT_DIR%\tricys_visual"
  call npm.cmd install
)

if exist "%ROOT_DIR%\tricys_goview\package.json" (
  cd /d "%ROOT_DIR%\tricys_goview"
  call npm.cmd install
)

cd /d "%ROOT_DIR%"
echo Dependencies installed successfully.
echo Python virtual environment: %VENV_DIR%
endlocal