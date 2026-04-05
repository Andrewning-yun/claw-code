@echo off
cd /d "%~dp0"
echo Starting Claude Chat Server...
echo.
echo If you see errors about missing packages, run:
echo   pip install -r requirements.txt
echo.
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
pause