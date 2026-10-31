@echo off
setlocal
title ADEM - IndicOCR (:8090)
rem Run on the GPU server. Frees port 8090 (from any other IndicOCR server) and starts this folder's service there.
rem It runs on this folder's .venv, or else on the Python of the server it replaces (which has IndicOCR installed).
cd /d "%~dp0"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr /c:":8090 "') do (
    for /f "delims=" %%e in ('powershell -NoProfile -Command "(Get-Process -Id %%p).Path"') do (
        echo Stopping the program on port 8090: %%e [PID %%p]
        if not defined PY echo %%~nxe | findstr /i "python" >nul && set "PY=%%e"
    )
    taskkill /F /PID %%p >nul 2>&1
)

if not defined PY (
    echo No IndicOCR install found: installing it in .venv. Accept the licence at https://huggingface.co/bodhan-ai/indic-ocr first.
    py -3.11 -m venv .venv || (echo [ERROR] Python 3.11 is needed: py -3.11 & pause & exit /b 1)
    .venv\Scripts\python.exe -m pip install -r requirements.txt || (pause & exit /b 1)
    .venv\Scripts\hf.exe auth whoami >nul 2>&1 || .venv\Scripts\hf.exe auth login
    .venv\Scripts\python.exe install.py || (pause & exit /b 1)
    set "PY=%~dp0.venv\Scripts\python.exe"
)

echo Starting IndicOCR on http://0.0.0.0:8090 with %PY% (requests are logged below) ...
"%PY%" -m uvicorn server:app --host 0.0.0.0 --port 8090
pause
