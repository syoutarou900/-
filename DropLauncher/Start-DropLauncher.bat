@echo off
chcp 932 >nul
cd /d %~dp0
echo ========================================
echo  ドロップランチャー（予備の起動方法です）
echo  本来は EXE版 DropLauncher.exe がおすすめです
echo ========================================
if not exist app.py (
  echo [エラー] app.py が見つかりません。
  echo ZIPファイルを「すべて展開」してから、展開したフォルダの中で実行してください。
  pause
  exit /b 1
)
if not exist requirements.txt (
  echo [エラー] requirements.txt が見つかりません。
  echo ZIPファイルを「すべて展開」してから、展開したフォルダの中で実行してください。
  pause
  exit /b 1
)
set PY=
where python >nul 2>nul && set PY=python
if not defined PY (
  where py >nul 2>nul && set PY=py
)
if not defined PY (
  echo [エラー] Python が見つかりません。EXE版を使ってください（Python不要です）。
  pause
  exit /b 1
)
echo ライブラリをインストール／確認しています（初回のみ約180MB）...
%PY% -m pip install --upgrade PySide6-Essentials Pillow openpyxl PyMuPDF pypdf imageio-ffmpeg
if errorlevel 1 (
  echo [エラー] ライブラリのインストールに失敗しました。ネット接続を確認してください。
  pause
  exit /b 1
)
echo ドロップランチャーを起動します。この窓は開いたままにしてください（閉じるとアプリも終了します）。
%PY% app.py
pause
