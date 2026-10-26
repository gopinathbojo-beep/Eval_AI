@echo off
title ADEM - Stop GPU Server
echo ========================================================
echo          Stopping ADEM GPU Server (Ollama + IndicOCR)
echo ========================================================
echo.

echo [1/2] Stopping IndicOCR on port 8090...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8090" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/2] Stopping Ollama...
taskkill /F /IM "ollama app.exe" >nul 2>&1
taskkill /F /IM ollama.exe >nul 2>&1

echo.
echo GPU server stopped.
pause
