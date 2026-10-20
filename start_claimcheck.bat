@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo   ClaimCheck Pro - Startup Script
echo ========================================================

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "APP=%~dp0streamlit_app\app.py"
set "PORT=8501"

if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment Python not found:
    echo         "%PYTHON%"
    echo [ERROR] Please make sure .venv exists.
    echo.
    pause
    exit /b 1
)

if not exist "%APP%" (
    echo [ERROR] Streamlit entry file not found:
    echo         "%APP%"
    echo.
    pause
    exit /b 1
)

netstat -ano | findstr ":8501 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [INFO] Port 8501 is already in use.
    echo [INFO] Switching to fallback port 8502.
    set "PORT=8502"
) else (
    echo [INFO] Port 8501 is available. Using port 8501.
)

echo.
echo [INFO] Server URL: http://127.0.0.1:%PORT%
echo [INFO] Opening default browser...
start http://127.0.0.1:%PORT%

echo [INFO] Starting Streamlit server...
echo [INFO] Press Ctrl+C to stop the server.
echo ========================================================
echo.

"%PYTHON%" -m streamlit run "%APP%" --server.address 127.0.0.1 --server.port %PORT% --server.headless true

if errorlevel 1 (
    echo.
    echo [ERROR] Streamlit exited with error.
    pause
    exit /b 1
)

pause
