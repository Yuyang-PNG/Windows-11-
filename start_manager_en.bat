@echo off
chcp 65001 >nul
title Process Priority Manager

echo ================================================
echo        Smart Process Priority Manager
echo ================================================
echo.

cd /d "%~dp0"

if exist "process_priority_manager.py" (
    echo Found main program, starting...
    python process_priority_manager.py --console
) else (
    echo ERROR: process_priority_manager.py not found
    pause
    exit /b 1
)