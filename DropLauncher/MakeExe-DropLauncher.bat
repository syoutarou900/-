@echo off
chcp 932 >nul
cd /d %~dp0
echo ========================================
echo  DropLauncher.exe を作成します
echo ========================================
if not exist app.py (
  echo [エラー] app.py が見つかりません。ZIPファイルを「すべて展開」してから実行してください。
  pause
  exit /b 1
)
if not exist requirements.txt (
  echo [エラー] requirements.txt が見つかりません。ZIPファイルを「すべて展開」してから実行してください。
  pause
  exit /b 1
)
set PY=
where python >nul 2>nul && set PY=python
if not defined PY (
  where py >nul 2>nul && set PY=py
)
if not defined PY (
  echo [エラー] Python が見つかりません。
  pause
  exit /b 1
)
echo ライブラリと PyInstaller をインストールしています...
%PY% -m pip install --upgrade PySide6-Essentials Pillow openpyxl PyMuPDF pypdf imageio-ffmpeg PyInstaller
if errorlevel 1 (
  echo [エラー] インストールに失敗しました。
  pause
  exit /b 1
)
%PY% -m PyInstaller --noconfirm --onefile --windowed --name DropLauncher --icon assets\icon.ico --add-data "assets;assets" --collect-all imageio_ffmpeg app.py
if errorlevel 1 (
  echo [エラー] exe の作成に失敗しました。
  pause
  exit /b 1
)
echo ========================================
echo  完成しました: dist\DropLauncher.exe
echo  このEXEは単体で起動でき、Pythonは不要です。
echo ========================================
pause
