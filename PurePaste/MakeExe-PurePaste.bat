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
  echo [Error] Python not found.
  pause
  exit /b 1
)
echo Installing libraries and PyInstaller...
%PY% -m pip install --upgrade PySide6-Essentials PyInstaller
if errorlevel 1 (
  echo [Error] Install failed.
  pause
  exit /b 1
)
%PY% -m PyInstaller --noconfirm --onefile --windowed --name PurePaste --icon assets\icon.ico --add-data "assets;assets" app.py
if errorlevel 1 (
  echo [Error] EXE build failed.
  pause
  exit /b 1
)
echo Done: dist\PurePaste.exe
pause
