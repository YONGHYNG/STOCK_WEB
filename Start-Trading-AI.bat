@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "APP_URL=http://127.0.0.1:8000"

if not exist "%PYTHON%" (
  echo [ERROR] Project virtual environment was not found.
  echo Expected: %PYTHON%
  pause
  exit /b 1
)

if not exist "%~dp0frontend\dist\index.html" (
  echo [INFO] Building the dashboard for the first run...
  pushd "%~dp0frontend"
  call npm run build
  if errorlevel 1 (
    popd
    echo [ERROR] Dashboard build failed.
    pause
    exit /b 1
  )
  popd
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [INFO] Starting Trading AI server...
  start "Trading AI Server" /min cmd /k "cd /d ""%~dp0"" ^&^& ""%PYTHON%"" -m api.main"
  powershell -NoProfile -Command "$ok=$false; 1..20 | ForEach-Object { if (Test-NetConnection 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue) { $ok=$true; break }; Start-Sleep -Milliseconds 500 }; if (-not $ok) { exit 1 }"
  if errorlevel 1 (
    echo [ERROR] Server did not start. Check the minimized Trading AI Server window.
    pause
    exit /b 1
  )
) else (
  echo [INFO] Trading AI server is already running.
)

start "" "%APP_URL%"
exit /b 0
