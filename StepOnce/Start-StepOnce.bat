@echo off
cd /d %~dp0
if not exist app.py (
  echo app.py が見つかりません。ZIPをすべて展開してから実行してください。
  pause
  exit /b 1
)
python -c "import PySide6, PIL" 2> nul
if errorlevel 1 (
  echo 必要なライブラリをインストールします（初回のみ）...
  python -m pip install -r requirements.txt
)
python app.py
if errorlevel 1 (
  echo.
  echo StepOnce がエラーで終了しました。上記の表示を確認してください。
  pause
)
