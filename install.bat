@echo off
REM Instala todo (una sola vez). Requiere Python 3.10-3.12 y Node.js.
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv || goto :err )
call .venv\Scripts\activate.bat || goto :err
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :err
cd frontend
call npm install || goto :err
cd ..
echo.
echo Instalacion completa. Ejecuta start.bat
pause
exit /b 0
:err
echo.
echo ERROR durante la instalacion. Revisa los mensajes de arriba.
pause
exit /b 1
