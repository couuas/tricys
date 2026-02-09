@echo off
setlocal

REM Root directory of this script
set ROOT_DIR=%~dp0

REM Optional: activate venv if present (for backend)
set VENV_ACTIVATE=%ROOT_DIR%venv\Scripts\activate.bat

REM --- Start tricys_backend ---
if exist "%VENV_ACTIVATE%" (
  start "tricys_backend" cmd /k "cd /d %ROOT_DIR% && call %VENV_ACTIVATE% && python -m uvicorn tricys_backend.main:app --host 0.0.0.0 --port 8000 --reload"
) else (
  start "tricys_backend" cmd /k "cd /d %ROOT_DIR% && python -m uvicorn tricys_backend.main:app --host 0.0.0.0 --port 8000 --reload"
)

REM --- Start tricys_visual ---
start "tricys_visual" cmd /k "cd /d %ROOT_DIR%tricys_visual && npm.cmd run dev"

REM --- Start tricys_goview ---
start "tricys_goview" cmd /k "cd /d %ROOT_DIR%tricys_goview && npm.cmd run dev"

endlocal
