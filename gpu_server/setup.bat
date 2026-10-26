@echo off
setlocal enabledelayedexpansion
title ADEM - GPU Server Setup (Ollama + IndicOCR)
echo ========================================================
echo     ADEM GPU Server Setup - run this on the GPU machine
echo     Ollama (InternVL) + IndicOCR, reachable from the LAN
echo ========================================================
echo.

:: Firewall rules and machine-wide Ollama settings need administrator rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Asking for administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
set "INDIC_DIR=%~dp0..\indic_ocr_service"
set "INTERNVL_MODEL=blaifa/InternVL3_5:4B"
set "PARALLEL=2"

if not exist "%INDIC_DIR%\server.py" (
    echo [ERROR] indic_ocr_service folder not found next to gpu_server.
    echo Copy both folders, or the whole Eval_AI folder, to this machine.
    pause
    exit /b 1
)

:: -----------------------------------------------------------------------------
echo [1/5] Checking Ollama and Python...
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Ollama is not installed. Install it from https://ollama.com/download and run this again.
    pause
    exit /b 1
)
py -3.11 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.11 is not installed. IndicOCR needs it: https://www.python.org/downloads/release/python-3119/
    pause
    exit /b 1
)
echo  - Ollama and Python 3.11 found.
echo.

:: -----------------------------------------------------------------------------
echo [2/5] Letting Ollama accept connections from the network...
setx OLLAMA_HOST "0.0.0.0:11434" /M >nul
setx OLLAMA_NUM_PARALLEL "%PARALLEL%" /M >nul
set "OLLAMA_HOST=0.0.0.0:11434"
set "OLLAMA_NUM_PARALLEL=%PARALLEL%"
echo  - OLLAMA_HOST=0.0.0.0:11434, OLLAMA_NUM_PARALLEL=%PARALLEL%
echo.

:: -----------------------------------------------------------------------------
echo [3/5] Opening the firewall to this network only (ports 11434, 8090 and ping)...
netsh advfirewall firewall delete rule name="ADEM Ollama (11434)" >nul 2>&1
netsh advfirewall firewall delete rule name="ADEM IndicOCR (8090)" >nul 2>&1
netsh advfirewall firewall delete rule name="ADEM Ping" >nul 2>&1
netsh advfirewall firewall add rule name="ADEM Ollama (11434)" dir=in action=allow protocol=TCP localport=11434 remoteip=localsubnet profile=any >nul
netsh advfirewall firewall add rule name="ADEM IndicOCR (8090)" dir=in action=allow protocol=TCP localport=8090 remoteip=localsubnet profile=any >nul
netsh advfirewall firewall add rule name="ADEM Ping" dir=in action=allow protocol=icmpv4:8,any remoteip=localsubnet profile=any >nul
echo  - Firewall rules added.
echo.

:: -----------------------------------------------------------------------------
echo [4/5] Restarting Ollama with the new settings and checking the model...
taskkill /F /IM "ollama app.exe" >nul 2>&1
taskkill /F /IM ollama.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start "ADEM - Ollama (:11434)" /min cmd /k "ollama serve"
timeout /t 5 /nobreak >nul
ollama list | findstr /i /c:"%INTERNVL_MODEL%" >nul 2>&1
if %errorlevel% neq 0 (
    echo  - Downloading %INTERNVL_MODEL% ...
    ollama pull %INTERNVL_MODEL%
) else (
    echo  - %INTERNVL_MODEL% already installed.
)
echo.

:: -----------------------------------------------------------------------------
echo [5/5] Setting up IndicOCR (first run downloads several GB)...
cd /d "%INDIC_DIR%"
if not exist .venv\Scripts\python.exe (
    py -3.11 -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create the IndicOCR virtual environment!
        pause
        exit /b 1
    )
)
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
.venv\Scripts\python.exe install.py
if !errorlevel! neq 0 (
    echo [WARNING] IndicOCR could not be installed. See indic_ocr_service\README.md, then run this again.
) else (
    echo  - IndicOCR installed.
)
echo.

cd /d "%~dp0"
echo ========================================================
echo GPU server setup complete. Start it with gpu_server\start.bat.
echo This machine's addresses (use one in the other PC's backend\.env):
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=*" %%j in ("%%i") do echo    %%j
echo ========================================================
pause
