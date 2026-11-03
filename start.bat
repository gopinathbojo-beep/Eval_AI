@echo off
setlocal
title Eval AI - Start
cd /d "%~dp0"

rem InternVL runs in Ollama on the remote model server; nothing AI runs on this PC.
set "INTERNVL_API_URL=http://192.168.1.9:11434"
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"INTERNVL_API_URL=" backend\.env 2^>nul') do set "INTERNVL_API_URL=%%b"
echo Checking InternVL at %INTERNVL_API_URL% ...
curl -s -m 5 "%INTERNVL_API_URL%/api/tags" >nul 2>&1
if errorlevel 1 (
  echo [WARNING] InternVL is not reachable at %INTERNVL_API_URL%.
  echo           Start Ollama on the model server with OLLAMA_HOST=0.0.0.0 and check INTERNVL_API_URL in backend\.env.
  echo           The app will start, but OCR and grading will fail until it is reachable.
) else (
  echo InternVL is reachable.
)

echo Starting backend at http://127.0.0.1:8000 ...
start "Eval AI Backend" cmd /k "cd /d "%~dp0backend" && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) else (python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload)"
timeout /t 2 /nobreak >nul
echo Starting frontend at http://localhost:5173 ...
start "Eval AI Frontend" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"
echo Open http://localhost:5173
pause
