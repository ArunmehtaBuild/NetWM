@echo off
setlocal

echo ========================================================
echo   NetWM Attack Forecasting Dashboard - 1-Click Launch
echo ========================================================
echo.

cd /d "%~dp0\.."

echo [1/4] Syncing API fixtures to frontend mock store...
python scripts\sync_fixtures.py

echo [2/4] Starting NetWM FastAPI backend on 127.0.0.1:5000...
start "NetWM Backend API" cmd /k "python -m uvicorn backend.server:app --host 127.0.0.1 --port 5000"

echo [3/4] Starting Frontend static server on 127.0.0.1:8080...
start "NetWM Frontend" cmd /k "python -m http.server 8080 --directory frontend --bind 127.0.0.1"

echo [4/4] Waiting for backend readiness...
rem A cold start imports torch and takes ~8 s; opening the browser earlier shows the mock fallback.
python backend\wait_ready.py --timeout 45

echo Opening dashboard in browser...
start http://127.0.0.1:8080

echo.
echo NetWM is running offline!
echo   - Backend API:  http://127.0.0.1:5000/docs
echo   - Dashboard:    http://127.0.0.1:8080
echo.
