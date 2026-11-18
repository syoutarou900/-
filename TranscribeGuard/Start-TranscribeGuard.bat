@echo off
chcp 932 >nul
cd /d %~dp0
echo ========================================
echo  転記見守り君の起動
echo  本体は EXE版 TranscribeGuard.exe を推奨します
echo ========================================
if not exist app.py (
  echo [エラー] app.py が見つかりません。
  echo ZIPファイルを「すべて展開」して、展開したフォルダーの中で実行してください。
  pause
  exit /b 1
)
if not exist requirements.txt (
  echo [エラー] requirements.txt が見つかりません。
  echo ZIPファイルを「すべて展開」して、展開したフォルダーの中で実行してください。
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
echo ライブラリのインストール／確認をしています（初回のみ約200MB）...
%PY% -m pip install --upgrade PySide6 openpyxl PyMuPDF Pillow pytesseract
if errorlevel 1 (
  echo [エラー] ライブラリのインストールに失敗しました。ネット接続を確認してください。
  pause
  exit /b 1
)
echo 転記見守り君を起動します。この黒い画面は開いたままにしてください（閉じるとアプリも終了します）。
%PY% app.py
pause
