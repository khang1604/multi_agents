@echo off
setlocal
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 "%~dp0ma.py" %*
) else (
    python "%~dp0ma.py" %*
)
exit /b %errorlevel%
