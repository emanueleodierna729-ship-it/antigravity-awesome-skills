@echo off
setlocal
cd /d "%~dp0"

echo.
echo   ╔══════════════════════════════════╗
echo   ║     FaceSwap Studio  v1.0        ║
echo   ╚══════════════════════════════════╝
echo.

where python >nul 2>&1 || (
  echo   [ERRORE] Python non trovato. Installa Python 3.10+
  pause & exit /b 1
)

if not exist ".venv" (
  echo   Creazione ambiente virtuale...
  python -m venv .venv
)

call .venv\Scripts\activate.bat

echo   Installazione dipendenze...
pip install -q --upgrade pip
pip install -q -r requirements.txt

if not exist "models\inswapper_128.onnx" (
  echo.
  echo   ATTENZIONE: modello mancante^^!
  echo   Scarica inswapper_128.onnx e mettilo in: %CD%\models\
  echo.
)

echo   Avvio server su http://localhost:8000
echo   Premi Ctrl+C per fermare
echo.

uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause
