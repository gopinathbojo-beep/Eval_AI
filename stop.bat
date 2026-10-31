@echo off
title ADEM - Stop
echo ========================================================
echo                      ADEM - Stop
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
