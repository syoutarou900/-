@echo off
chcp 932 >nul
cd /d %~dp0
if not exist app.py (
  echo [Error] app.py not found. Please extract the whole ZIP first.
  pause
  exit /b 1
)
set PY=
where python >nul 2>nul && set PY=python
if not defined PY (
  where py >nul 2>nul && set PY=py
)
if not defined PY (
  echo [Error] Python not found. Please install Python 3 first.
  pause
  exit /b 1
)
%PY% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo Installing libraries (first launch only)...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [Error] Install failed. Check your network connection.
    pause
    exit /b 1
  )
)
start "" /min %PY% app.py
