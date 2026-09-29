@echo off
REM Arranca backend (puerto 8000) y frontend (puerto 5173) y abre el navegador.
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Primero ejecuta install.bat
  pause
  exit /b 1
)
start "Restaurant Vision - Backend" cmd /k ".venv\Scripts\activate.bat && uvicorn backend.main:app --port 8000"
start "Restaurant Vision - Frontend" cmd /k "cd frontend && npm run dev"
timeout /t 6 /nobreak >nul
start http://localhost:5173
