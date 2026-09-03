@echo off
REM ============================================================
REM  Acoustic Eye - one-click launcher for Windows
REM  Double-click this file, or run it from a terminal.
REM  It creates the virtual environment, installs dependencies
REM  (first run only), then starts the web server.
REM ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [Acoustic Eye] Python was not found on your PATH.
  echo Install Python 3.10-3.12 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup, then run this again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [Acoustic Eye] Creating virtual environment ^(.venv^) ...
  python -m venv .venv
  if errorlevel 1 (
    echo [Acoustic Eye] Failed to create the virtual environment.
    pause
    exit /b 1
  )
)

echo [Acoustic Eye] Installing / checking dependencies ^(first run can take a few minutes^) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 (
  echo.
  echo [Acoustic Eye] Dependency installation failed. See the messages above.
  echo See README.md section 12 ^(Troubleshooting^) - especially the pyrtools notes.
  echo.
  pause
  exit /b 1
)

echo.
echo [Acoustic Eye] Starting the server. Your browser should be opened for you.
start "" "http://127.0.0.1:8000"
".venv\Scripts\python.exe" run.py %*

echo.
echo [Acoustic Eye] Server stopped.
pause
