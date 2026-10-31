@echo off
setlocal enabledelayedexpansion
title ADEM - Start
cd /d "%~dp0"
echo ========================================================
<<<<<<< 7c662e7
echo                      ADEM - Start
=======
echo                 Starting ADEM Services
echo   Backend (FastAPI) + Web (Vite)
echo   Models: wherever backend\.env points (Ollama + IndicOCR)
>>>>>>> kishore/Version2.0
echo ========================================================
echo.

set "BACKEND=%~dp0backend"
set "INDIC_DIR=%~dp0backend\indic_ocr_service"
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo [ERROR] Backend is not set up yet. Run setup.bat first.
    pause
    exit /b 1
)

rem Stop anything left from a previous run so the ports are free and fresh settings load
for %%p in (8000 5173 5174 5175 8081) do call :freeport %%p

set "INTERNVL_URL=http://127.0.0.1:11434"
set "INDIC_URL=http://127.0.0.1:8090"
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"INTERNVL_API_URL=" "%BACKEND%\.env" 2^>nul') do set "INTERNVL_URL=%%b"
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"INDIC_OCR_URL=" "%BACKEND%\.env" 2^>nul') do set "INDIC_URL=%%b"

<<<<<<< 7c662e7
echo [1/3] Models...
echo !INDIC_URL! | findstr /i "127.0.0.1 localhost" >nul
if !errorlevel! equ 0 if exist "%INDIC_DIR%\start.bat" (
    call :freeport 8090
    start "ADEM IndicOCR (8090)" /D "%INDIC_DIR%" cmd /k start.bat
    echo  - IndicOCR starting locally; the model takes a while to load
    timeout /t 10 /nobreak >nul
)
=======
echo [1/3] Models ...
call :check "IndicOCR" "!INDIC_URL!/health"
>>>>>>> kishore/Version2.0
call :check "Ollama  " "!INTERNVL_URL!/api/tags"
call :check "IndicOCR" "!INDIC_URL!/health"

<<<<<<< 7c662e7
echo [2/3] Backend on http://localhost:8000 ...
start "ADEM Backend (8000)" /D "%BACKEND%" cmd /k .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
timeout /t 3 /nobreak >nul

echo [3/3] Apps...
call :app web "ADEM Web (5173)"
call :app admin "ADEM Admin (5174)"
call :app parent "ADEM Parents (5175)"
if exist "%~dp0mobile\node_modules" (
    start "ADEM Mobile (Expo)" /D "%~dp0mobile" cmd /k npx.cmd expo start
) else (
    echo  - mobile has no node_modules: run setup.bat
)

echo.
echo ========================================================
echo   Backend   http://localhost:8000/api/health
echo   Web       http://localhost:5173   (schools and teachers)
echo   Admin     http://localhost:5174   (platform team)
echo   Parents   http://localhost:5175
echo   Mobile    Expo window (scan the QR code)
echo   Ollama    !INTERNVL_URL!
echo   IndicOCR  !INDIC_URL!
echo   Emails without SMTP: backend\data\outbox\
=======
echo [2/3] Starting Backend on http://0.0.0.0:8000 ...
start "ADEM - Backend (FastAPI :8000)" cmd /k "cd /d "%~dp0backend" && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) else (uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload)"

timeout /t 2 /nobreak >nul

echo [3/3] Starting Web Frontend on http://localhost:5173 ...
start "ADEM - Web Frontend (Vite :5173)" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"

echo.
echo ========================================================
echo All services launched:
echo   - Backend:       http://127.0.0.1:8000
echo   - Web Frontend:  http://localhost:5173
echo   - Ollama:        !INTERNVL_URL!
echo   - IndicOCR:      !INDIC_URL! (Tamil and other Indian languages)
>>>>>>> kishore/Version2.0
echo ========================================================
echo Close a window (or run stop.bat) to stop that service.
pause
exit /b 0

:app
if not exist "%~dp0frontend\node_modules" (
    echo  - frontend has no node_modules: run setup.bat
    exit /b 0
)
start "%~2" /D "%~dp0frontend\%~1" cmd /k npm.cmd run dev
exit /b 0

:freeport
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%~1 .*LISTENING"') do (
    if not "%%p"=="0" taskkill /PID %%p /T /F >nul 2>nul
)
exit /b 0

:check
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 '%~2' | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel% equ 0 (echo  - %~1 OK  %~2) else (echo  - [WARNING] %~1 not reachable at %~2)
exit /b 0
