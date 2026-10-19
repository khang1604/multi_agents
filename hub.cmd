@echo off
setlocal
rem Preserve the caller's project directory. Never cd to the Hub installation.
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 "%~dp0hub.py" %*
) else (
    python "%~dp0hub.py" %*
)
exit /b %errorlevel%
