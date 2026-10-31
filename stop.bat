@echo off
title ADEM - Stop
echo ========================================================
<<<<<<< 7c662e7
echo                      ADEM - Stop
=======
echo                 Stopping ADEM Services
echo ========================================================
echo.

echo [1/3] Stopping local IndicOCR on port 8090 (if running here)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8090" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/3] Stopping Backend on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [3/3] Stopping Web Frontend on port 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo ========================================================
echo ADEM services (IndicOCR, Backend, Frontend) have been stopped.
echo Note: models on the GPU machine keep running; stop them there with gpu_server\stop.bat.
>>>>>>> kishore/Version2.0
echo ========================================================
for %%p in (8090 8000 5173 5174 5175 8081) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r /c:":%%p .*LISTENING"') do (
        if not "%%a"=="0" (
            echo  - Port %%p: stopping PID %%a
            taskkill /PID %%a /T /F >nul 2>&1
        )
    )
)
echo.
echo Stopped: IndicOCR (8090), Backend (8000), Web (5173), Admin (5174), Parents (5175), Expo (8081).
echo Models on a separate GPU machine keep running; stop them there.
pause
