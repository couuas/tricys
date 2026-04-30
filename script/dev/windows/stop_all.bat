@echo off
setlocal

for %%I in ("%~dp0\..\..\..") do set ROOT_DIR=%%~fI
set PID_DIR=%ROOT_DIR%\.run

call :stop_service tricys_goview
call :stop_service tricys_visual
call :stop_service tricys_hdf5
call :stop_service tricys_backend

endlocal
goto :eof

:stop_service
set SERVICE_NAME=%~1
set PID_FILE=%PID_DIR%\%SERVICE_NAME%.pid

if not exist "%PID_FILE%" (
  echo %SERVICE_NAME% is not running.
  goto :eof
)

set /p SERVICE_PID=<"%PID_FILE%"
tasklist /FI "PID eq %SERVICE_PID%" | find "%SERVICE_PID%" >nul
if errorlevel 1 (
  echo %SERVICE_NAME% PID file existed but process %SERVICE_PID% was not running.
) else (
  taskkill /PID %SERVICE_PID% /T /F >nul
  echo Stopped %SERVICE_NAME% ^(PID %SERVICE_PID%^)
)

del /f /q "%PID_FILE%" >nul 2>nul
goto :eof
