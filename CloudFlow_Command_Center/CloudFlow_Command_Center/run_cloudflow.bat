@echo off
setlocal
cd /d "%~dp0"
title CloudFlow 2.0 - Command Center

echo ================================================
echo          CLOUDFLOW 2.0 COMMAND CENTER
echo ================================================
echo.

if not exist app.py (
  echo ERROR: app.py was not found. Please extract the complete ZIP first.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating the Python virtual environment...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 (
    echo Could not create the virtual environment. Check that Python is installed.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo Could not activate .venv.
  pause
  exit /b 1
)

echo [2/3] Installing/checking Flask dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check your internet connection and try again.
  pause
  exit /b 1
)

echo.
echo [3/3] Starting CloudFlow...
echo Keep this window open while using CloudFlow.
echo Open http://127.0.0.1:5000 in your browser.
echo Press Ctrl+C in this window to stop the server.
echo.
python app.py

echo.
echo CloudFlow has stopped.
pause
