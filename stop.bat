@echo off
title ADEM - Stop All Services
echo ========================================================
echo                 Stopping ADEM Services
echo ========================================================
echo.

echo [1/3] Stopping Backend on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/3] Stopping Web Frontend on port 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [3/3] Stopping Expo Metro on port 8081...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8081" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo ========================================================
echo ADEM services (Backend, Frontend, Expo) have been stopped.
echo Note: Ollama on remote machine "Gopinath" remains untouched.
echo ========================================================
echo.
pause
