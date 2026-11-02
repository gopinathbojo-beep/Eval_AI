@echo off
title Eval AI - Stop
for %%p in (8000 5173) do (
  for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%%p" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
)
echo Backend and frontend have been stopped.
pause
