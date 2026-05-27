@echo off
echo ===================================
echo  Surya Masterbatch — Setup & Start
echo ===================================

set ROOT=%~dp0
set VENV=%ROOT%.venv
set PYTHON=%VENV%\Scripts\python.exe
set PIP=%VENV%\Scripts\pip.exe

echo.
echo [0/4] Setting up Python virtual environment...
if not exist "%PYTHON%" (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo ERROR: Could not create virtual environment. Is Python installed?
        pause
        exit /b 1
    )
)

echo.
echo [1/4] Installing Python dependencies...
"%PIP%" install -r "%ROOT%app\backend\requirements.txt"

echo.
echo [2/4] Importing all data into database...
cd /d "%ROOT%app\backend"
"%PYTHON%" import_data.py

echo.
echo [3/4] Installing frontend dependencies...
cd /d "%ROOT%app\frontend"
call npm install

echo.
echo [4/4] Starting servers...
echo  Backend : http://localhost:5000
echo  Frontend: http://localhost:5173
echo.

start "Surya Backend" cmd /k ""%PYTHON%" "%ROOT%app\backend\run.py""
timeout /t 3 >nul
start "Surya Frontend" cmd /k "cd /d "%ROOT%app\frontend" && npm run dev"

echo.
echo Both servers started. Open http://localhost:5173 in your browser.
pause
