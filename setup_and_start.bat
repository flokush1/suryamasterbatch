@echo off
echo ===================================
echo  Surya Masterbatch — Setup & Start
echo ===================================

echo.
echo [1/4] Installing Python dependencies...
cd /d "%~dp0app\backend"
pip install -r requirements.txt

echo.
echo [2/4] Importing all data into database...
python import_data.py

echo.
echo [3/4] Installing frontend dependencies...
cd /d "%~dp0app\frontend"
call npm install

echo.
echo [4/4] Starting servers...
echo  Backend : http://localhost:5000
echo  Frontend: http://localhost:5173
echo.

start "Surya Backend" cmd /k "cd /d "%~dp0app\backend" && python run.py"
timeout /t 3 >nul
start "Surya Frontend" cmd /k "cd /d "%~dp0app\frontend" && npm run dev"

echo.
echo Both servers started. Open http://localhost:5173 in your browser.
pause
