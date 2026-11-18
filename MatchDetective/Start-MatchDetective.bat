@echo off
setlocal
cd /d %~dp0
if not exist app.py (
  echo app.py not found. Extract the ZIP first.
  pause
  exit /b 1
)
python -c "import PySide6, openpyxl" 2>nul
if errorlevel 1 (
  echo Installing libraries (first launch only)...
  python -m pip install PySide6 openpyxl
)
start "" pythonw app.py
