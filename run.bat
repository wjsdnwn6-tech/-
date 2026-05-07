@echo off
cd /d "%~dp0"

echo Starting Backend Server...
start "Backend" cmd /k "python -m uvicorn main:app --reload"

echo Starting Frontend Server...
cd frontend
start "Frontend" cmd /k "npm run dev"
cd ..

echo Servers started! Open http://localhost:5173 in your browser.
