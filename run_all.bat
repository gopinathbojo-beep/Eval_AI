@echo off
title ADEM Launcher
echo ========================================================
echo                 ADEM Application Suite
echo   FastAPI Backend + Vite Frontend + Expo Mobile App
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/4] Starting ADEM FastAPI Backend on http://0.0.0.0:8000 ...
start "ADEM - Backend (FastAPI :8000)" cmd /k "cd /d ""%~dp0backend"" && if exist .venv\Scripts\uvicorn.exe (.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload) else (uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload)"

timeout /t 2 /nobreak >nul

echo [2/4] Starting ADEM Web Frontend on http://localhost:5173 ...
start "ADEM - Web Frontend (Vite :5173)" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

timeout /t 2 /nobreak >nul

echo [3/4] Starting ADEM Mobile App (Expo)...
start "ADEM - Mobile App (Expo)" cmd /k "cd /d ""%~dp0mobile"" && npx expo start"

timeout /t 2 /nobreak >nul

echo [4/4] Starting Ollama Server on http://localhost:11434 ...
start "Ollama Server" cmd /k "ollama serve"
echo.
echo ========================================================
echo All 4 ADEM services have been launched in separate windows:
echo   - Backend:       http://127.0.0.1:8000
echo   - Web Frontend:  http://localhost:5173
echo   - Mobile App:    Expo Metro Bundler and QR Code
echo   - Ollama:        http://localhost:11434
echo ========================================================
echo.
pause
