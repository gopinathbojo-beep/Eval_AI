@echo off
setlocal enabledelayedexpansion
title Eval AI - Setup
cd /d "%~dp0"

where node >nul 2>&1 || (echo [ERROR] Install Node.js 24.& pause & exit /b 1)
where python >nul 2>&1 || (echo [ERROR] Install Python 3.11.& pause & exit /b 1)

if not exist backend\.venv\Scripts\python.exe python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (echo [ERROR] Backend installation failed.& pause & exit /b 1)

if not exist backend\.env copy backend\.env.example backend\.env >nul
if not exist .env copy .env.example .env >nul

pushd frontend
call npm.cmd install --loglevel=error
if errorlevel 1 (popd & echo [ERROR] Frontend installation failed.& pause & exit /b 1)
popd

pushd backend
.venv\Scripts\python.exe -c "from app.database import SessionLocal, init_db; from app.services.admin_accounts import ensure_owner; init_db(); db=SessionLocal(); ensure_owner(db); db.close()"
popd

echo Setup complete. Add OPENROUTER_API_KEY to .env or backend\.env, then run start.bat.
pause
