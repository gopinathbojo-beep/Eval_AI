@echo off
setlocal enabledelayedexpansion
title ADEM - Setup
cd /d "%~dp0"
<<<<<<< 7c662e7
echo ========================================================
echo                      ADEM - Setup
echo   Backend + IndicOCR + Web + Admin + Parents (+ Mobile)
echo ========================================================
echo.

set "BACKEND=%~dp0backend"
=======

:: -----------------------------------------------------------------------------
:: Step 1: Check Pre-requisites (Node.js, npm, Python)
:: -----------------------------------------------------------------------------
echo [1/6] Checking system prerequisites...

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not found in PATH!
    echo Please install Node.js 24 from https://nodejs.org
    pause
    exit /b 1
)

where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm is not found in PATH!
    pause
    exit /b 1
)

set PYTHON_CMD=
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3.11 --version >nul 2>&1
    if !errorlevel! equ 0 (
        set PYTHON_CMD=py -3.11
    ) else (
        py -3 --version >nul 2>&1
        if !errorlevel! equ 0 set PYTHON_CMD=py -3
    )
)

if "!PYTHON_CMD!"=="" (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python
    ) else (
        echo [ERROR] Python 3 is not found in PATH!
        echo Please install Python 3.10, 3.11, or 3.12 from https://www.python.org
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%v in ('node -v') do set NODE_VER=%%v
echo  - Found Node.js: !NODE_VER!
echo  - Using Python:  !PYTHON_CMD!
echo.

:: -----------------------------------------------------------------------------
:: Step 2: Setup Backend Virtual Environment
:: -----------------------------------------------------------------------------
echo [2/6] Setting up Python virtual environment (backend\.venv)...
cd /d "%~dp0backend"
>>>>>>> kishore/Version2.0

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

<<<<<<< 7c662e7
echo [3/5] IndicOCR (backend\indic_ocr_service)...
=======
:: -----------------------------------------------------------------------------
:: Step 3: Configure Environment (.env) & Data Storage
:: -----------------------------------------------------------------------------
echo [3/6] Configuring environment settings...
cd /d "%~dp0"

if not exist data mkdir data

if not exist backend\.env (
    if exist backend\.env.example (
        copy backend\.env.example backend\.env >nul
        echo  - Created backend\.env from template.
    ) else (
        echo INTERNVL_ENABLED=true> backend\.env
        echo INTERNVL_MODEL=blaifa/InternVL3_5:4B>> backend\.env
        echo INTERNVL_API_URL=http://127.0.0.1:11434>> backend\.env
        echo INTERNVL_TIMEOUT=300>> backend\.env
        echo SECRET_KEY=>> backend\.env
        echo ACCESS_TOKEN_MINUTES=480>> backend\.env
        echo DATA_DIR=../data>> backend\.env
        echo PDF_RENDER_DPI=300>> backend\.env
        echo MAX_UPLOAD_MB=50>> backend\.env
        echo CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173>> backend\.env
        echo  - Generated default backend\.env file.
    )
) else (
    echo  - backend\.env already exists.
)

:: Tamil and other Indian-language subjects are read by the local IndicOCR service (step 5)
findstr /b /c:"INDIC_OCR_ENABLED=" backend\.env >nul 2>&1
if !errorlevel! neq 0 (
    echo.>> backend\.env
    echo INDIC_OCR_ENABLED=true>> backend\.env
    echo INDIC_OCR_URL=http://127.0.0.1:8090>> backend\.env
    echo  - Added IndicOCR settings to backend\.env
)
echo.

:: -----------------------------------------------------------------------------
:: Step 4: Initialize Database & Default Admin/Teacher Account
:: -----------------------------------------------------------------------------
echo [4/6] Initializing database and protected owner account...
cd /d "%~dp0backend"
.venv\Scripts\python.exe -c "from app.database import SessionLocal, init_db; from app.services.admin_accounts import ensure_owner; init_db(); db=SessionLocal(); ensure_owner(db); db.close(); print('  - Database ready. Register a school or parent account, or use owner Google sign-in.')"
echo.

:: -----------------------------------------------------------------------------
:: Step 5: IndicOCR Service (Tamil and other Indian-language subjects)
:: -----------------------------------------------------------------------------
echo [5/6] Setting up IndicOCR service (indic_ocr_service\.venv)...
cd /d "%~dp0"
>>>>>>> kishore/Version2.0
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

<<<<<<< 7c662e7
=======
:: -----------------------------------------------------------------------------
:: Step 6: Install Frontend Dependencies
:: -----------------------------------------------------------------------------
:frontend
echo [6/6] Installing Web Frontend dependencies (npm install)...
cd /d "%~dp0frontend"
call npm.cmd install --loglevel=error
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install frontend dependencies!
    pause
    exit /b 1
)
echo  - Frontend dependencies installed successfully.
echo.

:: -----------------------------------------------------------------------------
:: Completion Summary
:: -----------------------------------------------------------------------------
cd /d "%~dp0"
>>>>>>> kishore/Version2.0
echo ========================================================
echo  Setup complete. Double-click start.bat to run everything.
echo    Admin    http://localhost:5174   admin@adem.local / ChangeMe123
echo    Web      http://localhost:5173   rao@school.org   / password123
echo    Parents  http://localhost:5175   parent@adem.local / password123
echo ========================================================
<<<<<<< 7c662e7
=======
echo.
echo Login Credentials:
echo   - Schools and parents: register at /register
echo   - Teachers: use credentials from school management
echo.
echo How to run:
echo   - Launch services: Double-click "start.bat" (starts IndicOCR here only if backend\.env points to this PC)
echo   - Stop services:   Double-click "stop.bat"
echo.
>>>>>>> kishore/Version2.0
pause
