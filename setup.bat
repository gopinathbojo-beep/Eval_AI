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
echo [1/6] Checking system prerequisites...

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
echo [2/6] Setting up Python virtual environment (backend\.venv)...
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
echo.

:: -----------------------------------------------------------------------------
:: Step 4: Initialize Database & Default Admin/Teacher Account
:: -----------------------------------------------------------------------------
echo [4/6] Initializing database and default teacher account...
cd /d "%~dp0backend"
.venv\Scripts\python.exe -c "from app.database import SessionLocal, init_db; from app.models import Teacher; from app.security import hash_password; init_db(); db=SessionLocal(); (not db.query(Teacher).filter_by(email='rao@school.org').first()) and (db.add(Teacher(name='Ms Rao', email='rao@school.org', password_hash=hash_password('password123'))), db.commit()); db.close(); print('  - Database ready. Default teacher: rao@school.org / password123')"
echo.

:: -----------------------------------------------------------------------------
:: Step 5: Install Frontend Dependencies
:: -----------------------------------------------------------------------------
echo [5/6] Installing Web Frontend dependencies (npm install)...
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
:: Step 6: Install Mobile App Dependencies
:: -----------------------------------------------------------------------------
echo [6/6] Installing Mobile App dependencies (Expo)...
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
echo   - Launch services: Double-click "start.bat"
echo   - Stop services:   Double-click "stop.bat"
echo.
pause

