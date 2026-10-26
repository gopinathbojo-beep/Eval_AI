@echo off
setlocal
title ADEM - Start GPU Server
echo ========================================================
echo          Starting ADEM GPU Server (Ollama + IndicOCR)
echo ========================================================
echo.
cd /d "%~dp0"
set "INDIC_DIR=%~dp0..\indic_ocr_service"
set "OLLAMA_HOST=0.0.0.0:11434"
set "OLLAMA_NUM_PARALLEL=2"

echo [1/2] Ollama on port 11434 ...
netstat -ano | findstr "LISTENING" | findstr /c:"0.0.0.0:11434" >nul
if %errorlevel% equ 0 (
    echo  - Already running and reachable from the network.
) else (
    rem running only for this machine (127.0.0.1), or not at all: restart it for the network
    taskkill /F /IM "ollama app.exe" >nul 2>&1
    taskkill /F /IM ollama.exe >nul 2>&1
    timeout /t 2 /nobreak >nul
    start "ADEM - Ollama (:11434)" /min cmd /k "ollama serve"
    echo  - Started.
)

echo [2/2] IndicOCR on port 8090 ...
netstat -ano | findstr "LISTENING" | findstr /c:":8090" >nul
if %errorlevel% equ 0 (
    echo  - Already running.
) else if exist "%INDIC_DIR%\.venv\Scripts\python.exe" (
    start "ADEM - IndicOCR (:8090)" cmd /k "cd /d "%INDIC_DIR%" && .venv\Scripts\python.exe -m uvicorn server:app --host 0.0.0.0 --port 8090"
    echo  - Started.
) else (
    echo  - [ERROR] IndicOCR is not installed. Run gpu_server\setup.bat first.
)

echo.
echo ========================================================
echo GPU server running. Other PCs reach it at:
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=*" %%j in ("%%i") do echo    Ollama http://%%j:11434    IndicOCR http://%%j:8090
echo Keep this machine awake while ADEM is in use.
echo ========================================================
pause
