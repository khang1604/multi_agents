@echo off
setlocal enabledelayedexpansion

:: Multi Agents — Windows Command Prompt launcher setup

:: 1. Locate Python 3.11+
set "PY_CMD="
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_CMD=py -3"
    )
)

if not defined PY_CMD (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
        if !errorlevel! equ 0 (
            set "PY_CMD=python"
        )
    )
)

if not defined PY_CMD (
    echo Python 3.11+ is required. Install it before running setup. >&2
    exit /b 1
)

:: 2. Silently install 'ma' launcher and configure PATH
%PY_CMD% "%~dp0cli\ma.py" install-command >nul 2>&1
if %errorlevel% neq 0 (
    echo Setup failed during launcher installation. >&2
    exit /b %errorlevel%
)

:: 3. Shims for detected AI CLIs
set "BIN_DIR=%USERPROFILE%\.local\share\MultiAgents\runtime\bin"
if exist "%BIN_DIR%" (
    if exist "%USERPROFILE%\.gemini\bin\agy.cmd" (
        if not exist "%BIN_DIR%\agy.cmd" (
            (
                echo @echo off
                echo "%USERPROFILE%\.gemini\bin\agy.cmd" %%*
                echo exit /b %%errorlevel%%
            ) > "%BIN_DIR%\agy.cmd"
        )
    ) else if exist "%USERPROFILE%\.gemini\bin\agy.exe" (
        if not exist "%BIN_DIR%\agy.cmd" (
            (
                echo @echo off
                echo "%USERPROFILE%\.gemini\bin\agy.exe" %%*
                echo exit /b %%errorlevel%%
            ) > "%BIN_DIR%\agy.cmd"
        )
    )

    if exist "%USERPROFILE%\.codex\plugins\.plugin-appserver\codex.exe" (
        if not exist "%BIN_DIR%\codex.cmd" (
            (
                echo @echo off
                echo "%USERPROFILE%\.codex\plugins\.plugin-appserver\codex.exe" %%*
                echo exit /b %%errorlevel%%
            ) > "%BIN_DIR%\codex.cmd"
        )
    )
)

:: 4. Completion message
echo Setup complete!

