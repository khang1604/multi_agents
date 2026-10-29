@echo off
setlocal
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 "%~dp0..\cli\ma.py" %*
) else (
    python "%~dp0..\cli\ma.py" %*
)
exit /b %errorlevel%
