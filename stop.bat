@echo off
title ADEM - Stop All Services
echo ========================================================
echo                 Stopping ADEM Services
echo ========================================================
echo.

echo [1/4] Stopping Backend on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/4] Stopping Web Frontend on port 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [3/4] Stopping Expo Metro on port 8081...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8081" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [4/4] Stopping Ollama server...
taskkill /F /IM ollama.exe /IM "ollama app.exe" >nul 2>&1

echo.
echo ========================================================
echo All ADEM services (Backend, Frontend, Expo, Ollama) have been stopped.
echo ========================================================
echo.
pause
