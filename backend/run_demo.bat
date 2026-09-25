@echo off
setlocal

echo ========================================================
echo   NetWM Attack Forecasting Dashboard - 1-Click Launch
echo ========================================================
echo.

cd /d "%~dp0\.."

echo [1/3] Starting NetWM FastAPI backend on 127.0.0.1:5000...
start "NetWM Backend API" cmd /k "python -m uvicorn backend.server:app --host 127.0.0.1 --port 5000"

echo [2/3] Starting Frontend static server on 127.0.0.1:8080...
start "NetWM Frontend" cmd /k "python -m http.server 8080 --directory frontend --bind 127.0.0.1"

echo [3/3] Opening dashboard in browser...
timeout /t 2 /nobreak >nul
start http://127.0.0.1:8080

echo.
echo NetWM is running offline!
echo   - Backend API:  http://127.0.0.1:5000/docs
echo   - Dashboard:    http://127.0.0.1:8080
echo.
