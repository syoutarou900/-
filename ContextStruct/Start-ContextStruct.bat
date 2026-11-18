@echo off
cd /d %~dp0
echo ============================================
echo  ContextStruct - Startup
echo ============================================
if not exist app.py goto NOFILE
if not exist requirements.txt goto NOFILE
echo Checking / installing libraries (first launch only, may take a while)...
python -m pip install --upgrade PySide6 PyMuPDF openpyxl Pillow pytesseract opencv-python-headless numpy
echo.
echo Starting ContextStruct...
echo Keep this window open while the app runs. Closing it closes the app.
python app.py
echo.
echo App closed.
pause
exit /b
:NOFILE
echo [ERROR] app.py or requirements.txt was not found next to this file.
echo Please EXTRACT the whole ZIP first, then open the extracted folder
echo and double-click Start-ContextStruct.bat inside it.
pause
exit /b
