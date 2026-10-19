@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 scripts\menu.py
) else (
    python scripts\menu.py
)
if errorlevel 1 pause
endlocal
