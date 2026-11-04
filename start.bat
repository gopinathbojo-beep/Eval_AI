@echo off
setlocal
title Eval AI - Start
cd /d "%~dp0"

rem Every AI step uses OpenRouter (OPENROUTER_API_KEY and OPENROUTER_MODEL in backend\.env).
findstr /b /c:"OPENROUTER_API_KEY=" .env backend\.env 2>nul | findstr /v /r "OPENROUTER_API_KEY=$" >nul
if errorlevel 1 (
  echo [ERROR] Set OPENROUTER_API_KEY in backend\.env first.
  pause
  exit /b 1
)
curl -s -m 5 https://openrouter.ai/api/v1/models >nul 2>&1
if errorlevel 1 (
  echo [WARNING] OpenRouter is not reachable. Check the internet connection; OCR and grading fail until it is.
)

echo Starting backend at http://127.0.0.1:8000 ...
start "Eval AI Backend" cmd /k "cd /d "%~dp0backend" && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app) else (python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app)"
timeout /t 2 /nobreak >nul
echo Starting frontend at http://localhost:5173 ...
start "Eval AI Frontend" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"
echo Open http://localhost:5173
pause
