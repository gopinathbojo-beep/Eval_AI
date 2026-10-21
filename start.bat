@echo off
git title ADEM - Start All Services
echo ========================================================
echo                 Starting ADEM Services
echo   Backend (FastAPI) + Web (Vite) + Mobile (Expo) + Ollama
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/4] Starting Backend on http://0.0.0.0:8000 ...
start "ADEM - Backend (FastAPI :8000)" cmd /k "cd /d "%~dp0backend" && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) else (uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload)"

timeout /t 2 /nobreak >nul

echo [2/4] Starting Web Frontend on http://localhost:5173 ...
start "ADEM - Web Frontend (Vite :5173)" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"
.\star
timeout /t 2 /nobreak >nul

echo [3/4] Starting Mobile App (Expo)...
start "ADEM - Mobile App (Expo)" cmd /k "cd /d "%~dp0mobile" && npx.cmd expo start"

timeout /t 2 /nobreak >nul

netstat -ano | findstr ":11434" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo [4/4] Starting Ollama Server on http://localhost:11434 ...
    start "ADEM - Ollama Server (:11434)" cmd /k "ollama serve"
) else (
    echo [4/4] Ollama Server is already running on port 11434.
)

echo.
echo ========================================================
echo All services launched:
echo   - Backend:       http://127.0.0.1:8000
echo   - Web Frontend:  http://localhost:5173
echo   - Mobile App:    Expo Metro Bundler
echo   - Ollama Server: http://localhost:11434
echo ========================================================
echo.
pause
