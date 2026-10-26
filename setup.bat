@echo off
setlocal enabledelayedexpansion
title ADEM - Complete Product Setup
echo ========================================================
echo          ADEM (Eval AI) - Automated Product Setup
echo ========================================================
echo.

cd /d "%~dp0"

:: -----------------------------------------------------------------------------
:: Step 1: Check Pre-requisites (Node.js, npm, Python)
:: -----------------------------------------------------------------------------
echo [1/7] Checking system prerequisites...

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not found in PATH!
    echo Please install Node.js 18+ from https://nodejs.org
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
echo [2/7] Setting up Python virtual environment (backend\.venv)...
cd /d "%~dp0backend"

if not exist .venv\Scripts\python.exe (
    echo  - Creating virtual environment...
    !PYTHON_CMD! -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
) else (
    echo  - Existing virtual environment detected.
)

echo  - Upgrading pip...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet

echo  - Installing backend requirements...
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install backend requirements!
    pause
    exit /b 1
)
echo  - Backend packages installed successfully.
echo.

:: -----------------------------------------------------------------------------
:: Step 3: Configure Environment (.env) & Data Storage
:: -----------------------------------------------------------------------------
echo [3/7] Configuring environment settings...
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
echo [4/7] Initializing database and default teacher account...
cd /d "%~dp0backend"
.venv\Scripts\python.exe -c "from app.database import SessionLocal, init_db; from app.models import Teacher; from app.security import hash_password; init_db(); db=SessionLocal(); (not db.query(Teacher).filter_by(email='rao@school.org').first()) and (db.add(Teacher(name='Ms Rao', email='rao@school.org', password_hash=hash_password('password123'))), db.commit()); db.close(); print('  - Database ready. Default teacher: rao@school.org / password123')"
echo.

:: -----------------------------------------------------------------------------
:: Step 5: IndicOCR Service (Tamil and other Indian-language subjects)
:: -----------------------------------------------------------------------------
echo [5/7] Setting up IndicOCR service (indic_ocr_service\.venv)...
cd /d "%~dp0"
set "INDIC_URL=http://127.0.0.1:8090"
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"INDIC_OCR_URL=" backend\.env 2^>nul') do set "INDIC_URL=%%b"
echo !INDIC_URL! | findstr /i "127.0.0.1 localhost" >nul
if !errorlevel! neq 0 (
    echo  - Skipped: IndicOCR runs on another machine ^(!INDIC_URL!^). Set it up there with gpu_server\setup.bat.
    echo.
    goto :frontend
)
cd /d "%~dp0indic_ocr_service"

if not exist .venv\Scripts\python.exe (
    echo  - Creating virtual environment...
    !PYTHON_CMD! -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create the IndicOCR virtual environment!
        pause
        exit /b 1
    )
) else (
    echo  - Existing virtual environment detected.
)

echo  - Installing service requirements...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install IndicOCR service requirements!
    pause
    exit /b 1
)

.venv\Scripts\hf.exe auth whoami >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo  - IndicOCR needs a Hugging Face login to download the model:
    echo      1. Accept the licence at https://huggingface.co/bodhan-ai/indic-ocr
    echo      2. Create a Read token at https://huggingface.co/settings/tokens
    echo      3. Paste the token below
    .venv\Scripts\hf.exe auth login
)

echo  - Downloading the model and installing PyTorch (first run: several GB)...
.venv\Scripts\python.exe install.py
if !errorlevel! neq 0 (
    echo [WARNING] IndicOCR could not be installed. Tamil and other Indian-language subjects
    echo           cannot be read until this is fixed. Other subjects work normally.
    echo           Re-run setup.bat or see indic_ocr_service\README.md
) else (
    echo  - IndicOCR installed successfully.
)
echo.

:: -----------------------------------------------------------------------------
:: Step 6: Install Frontend Dependencies
:: -----------------------------------------------------------------------------
:frontend
echo [6/7] Installing Web Frontend dependencies (npm install)...
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
:: Step 7: Install Mobile App Dependencies
:: -----------------------------------------------------------------------------
echo [7/7] Installing Mobile App dependencies (Expo)...
cd /d "%~dp0mobile"
call npm.cmd install --loglevel=error
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install mobile dependencies!
    pause
    exit /b 1
)
echo  - Mobile dependencies installed successfully.
echo.

:: -----------------------------------------------------------------------------
:: Completion Summary
:: -----------------------------------------------------------------------------
cd /d "%~dp0"
echo ========================================================
echo           ADEM Product Setup Complete!
echo ========================================================
echo.
echo Login Credentials:
echo   - Email / User ID: rao@school.org
echo   - Password:        password123
echo.
echo How to run:
echo   - Launch services: Double-click "start.bat" (starts IndicOCR here only if backend\.env points to this PC)
echo   - Stop services:   Double-click "stop.bat"
echo.
pause

