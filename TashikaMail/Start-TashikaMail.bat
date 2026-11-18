@echo off
chcp 65001 > nul
cd /d %~dp0
if not exist app.py (
  echo app.py not found. Please extract the whole ZIP first.
  pause
  exit /b 1
)
python -c "import PySide6, pypdf, openpyxl, fitz, PIL" 2> nul
if errorlevel 1 (
  echo Installing required libraries (first run only)...
  python -m pip install -r requirements.txt
)
python app.py
if errorlevel 1 (
  echo.
  echo TashikaMail stopped with an error. See above.
  pause
)
