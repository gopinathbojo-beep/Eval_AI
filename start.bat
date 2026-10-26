@echo off
setlocal enabledelayedexpansion
title ADEM - Start All Services
echo ========================================================
echo                 Starting ADEM Services
echo   Backend (FastAPI) + Web (Vite) + Mobile (Expo)
echo   Models: wherever backend\.env points (Ollama + IndicOCR)
echo ========================================================
echo.

cd /d "%~dp0"

set "INTERNVL_URL=http://127.0.0.1:11434"
set "INDIC_URL=http://127.0.0.1:8090"
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"INTERNVL_API_URL=" backend\.env 2^>nul') do set "INTERNVL_URL=%%b"
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"INDIC_OCR_URL=" backend\.env 2^>nul') do set "INDIC_URL=%%b"

echo [1/4] Models ...
echo !INDIC_URL! | findstr /i "127.0.0.1 localhost" >nul
if !errorlevel! equ 0 (
    if exist "%~dp0indic_ocr_service\.venv\Scripts\python.exe" (
        start "ADEM - IndicOCR (:8090)" cmd /k "cd /d "%~dp0indic_ocr_service" && .venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8090"
        echo  - Started local IndicOCR on !INDIC_URL!
        timeout /t 2 /nobreak >nul
    ) else (
        echo  - Skipped local IndicOCR: not installed. Run setup.bat to read Tamil subjects.
    )
) else (
    echo  - IndicOCR runs on another machine: !INDIC_URL!
    call :check "IndicOCR" "!INDIC_URL!/health"
)
call :check "Ollama  " "!INTERNVL_URL!/api/tags"

echo [2/4] Starting Backend on http://0.0.0.0:8000 ...
start "ADEM - Backend (FastAPI :8000)" cmd /k "cd /d "%~dp0backend" && if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) else (uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload)"

timeout /t 2 /nobreak >nul

echo [3/4] Starting Web Frontend on http://localhost:5173 ...
start "ADEM - Web Frontend (Vite :5173)" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"

timeout /t 2 /nobreak >nul

echo [4/4] Starting Mobile App (Expo)...
start "ADEM - Mobile App (Expo)" cmd /k "cd /d "%~dp0mobile" && npx.cmd expo start"

echo.
echo ========================================================
echo All services launched:
echo   - Backend:       http://127.0.0.1:8000
echo   - Web Frontend:  http://localhost:5173
echo   - Mobile App:    Expo Metro Bundler
echo   - Ollama:        !INTERNVL_URL!
echo   - IndicOCR:      !INDIC_URL! (Tamil and other Indian languages)
echo ========================================================
echo.
pause
exit /b

:check
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 '%~2' | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel% equ 0 (
    echo  - %~1 OK        %~2
) else (
    echo  - [WARNING] %~1 NOT reachable at %~2
    echo    On the GPU machine run gpu_server\start.bat, and check it is on and on this network.
)
exit /b
