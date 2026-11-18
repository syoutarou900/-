@echo off
cd /d %~dp0
echo ============================================================
echo  ContextStruct - Download ALL VLM models (3B + 7B, ~8.3GB)
echo  For distributors: run once, then re-zip app + models.
echo ============================================================
if not exist download_models.py goto NOFILE
if not exist app.py goto NOFILE
echo Downloading models. This takes a while (approx. 8.3 GB total)...
python download_models.py
echo.
echo Finished. The models are in your ContextStruct data folder.
echo To build a full package, copy the "models" folder next to app.py
echo and re-zip the whole ContextStruct folder.
pause
exit /b
:NOFILE
echo [ERROR] download_models.py or app.py was not found next to this file.
echo Please EXTRACT the whole ZIP first, then open the extracted folder
echo and double-click Download-Models.bat inside it.
pause
exit /b
