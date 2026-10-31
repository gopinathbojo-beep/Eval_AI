@echo off
setlocal enabledelayedexpansion
title ADEM - Setup
cd /d "%~dp0"
echo ========================================================
echo                      ADEM - Setup
echo   Backend + IndicOCR + Web + Admin + Parents (+ Mobile)
echo ========================================================
echo.

set "BACKEND=%~dp0backend"

echo [1/5] Checking prerequisites...
where npm >nul 2>&1 || (echo [ERROR] npm not found. Install Node.js 18+ from https://nodejs.org & pause & exit /b 1)
py -3.11 --version >nul 2>&1 || (echo [ERROR] Python 3.11 not found. Install it from https://www.python.org & pause & exit /b 1)
echo  - OK
echo.

echo [2/5] Backend (backend\.venv)...
cd /d "%BACKEND%"
if not exist .venv\Scripts\python.exe (
    py -3.11 -m venv .venv || (echo [ERROR] Could not create the backend venv. & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet || (echo [ERROR] Backend packages failed. & pause & exit /b 1)
if not exist .env (
    copy .env.example .env >nul
    echo  - Created .env from .env.example
)
.venv\Scripts\python.exe scripts\seed_dev.py
echo.

echo [3/5] IndicOCR (backend\indic_ocr_service)...
set "INDIC_URL=http://127.0.0.1:8090"
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"INDIC_OCR_URL=" .env 2^>nul') do set "INDIC_URL=%%b"
echo !INDIC_URL! | findstr /i "127.0.0.1 localhost" >nul
if !errorlevel! neq 0 (
    echo  - Skipped: IndicOCR runs on another machine ^(!INDIC_URL!^).
) else (
    cd /d "%BACKEND%\indic_ocr_service"
    if not exist .venv\Scripts\python.exe py -3.11 -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    .venv\Scripts\python.exe -c "import huggingface_hub; huggingface_hub.whoami()" >nul 2>&1 || .venv\Scripts\python.exe -c "import huggingface_hub; huggingface_hub.login()"
    .venv\Scripts\python.exe install.py || echo [WARNING] IndicOCR not installed; Tamil subjects cannot be read until it is.
)
echo.

echo [4/5] Web, Admin and Parents apps (one shared npm install in frontend)...
pushd "%~dp0frontend"
call npm.cmd install --loglevel=error --no-audit --no-fund || (popd & echo [ERROR] npm install failed in frontend & pause & exit /b 1)
popd
echo.

echo [5/5] Mobile app (optional)...
if exist "%~dp0mobile\package.json" (
    pushd "%~dp0mobile"
    call npm.cmd install --loglevel=error --no-audit --no-fund
    popd
) else (
    echo  - Skipped: no mobile folder.
)
echo.

echo ========================================================
echo  Setup complete. Double-click start.bat to run everything.
echo    Admin    http://localhost:5174   admin@adem.local / ChangeMe123
echo    Web      http://localhost:5173   rao@school.org   / password123
echo    Parents  http://localhost:5175   parent@adem.local / password123
echo ========================================================
pause
