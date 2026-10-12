@echo off
rem Double-click: starts the dashboard and opens it in the browser (reachable from this machine only).
rem Stop: close this window or press Ctrl+C.
chcp 65001 >nul
cd /d "%~dp0"
python -m aos serve
if errorlevel 1 (
  echo.
  echo Something went wrong. "python -m aos doctor" shows what is missing.
  pause
)
