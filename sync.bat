@echo off
setlocal
echo ===================================================
echo   TwinVolt — 1-Click GitHub Sync
echo ===================================================
echo.

set /p MSG="Enter commit message (Press Enter for auto-timestamp): "

if "%MSG%"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\git_sync.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\git_sync.ps1" -Message "%MSG%"
)

echo.
pause
