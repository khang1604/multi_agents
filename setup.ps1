# Multi Agents — Windows PowerShell launcher setup
$ErrorActionPreference = 'Stop'

# 1. Locate Python 3.11+
$pyExe = $null
$pyArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    $verCheck = & py -3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pyExe = 'py'
        $pyArgs = @('-3')
    }
}

if (-not $pyExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $verCheck = & python -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pyExe = 'python'
        $pyArgs = @()
    }
}

if (-not $pyExe) {
    [Console]::Error.WriteLine("Python 3.11+ is required. Install it before running setup.")
    exit 1
}

$entry = Join-Path $PSScriptRoot 'cli\ma.py'

# 2. Silently install 'ma' launcher and configure PATH
& $pyExe @pyArgs $entry install-command *>$null
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("Setup failed during launcher installation.")
    exit $LASTEXITCODE
}

# 3. Create shims for detected AI CLIs (agy, codex) in runtime\bin
$binDir = Join-Path $HOME '.local\share\MultiAgents\runtime\bin'
if (Test-Path $binDir) {
    # agy detection
    $agyTarget = $null
    $agyCandidates = @(
        (Join-Path $HOME '.gemini\bin\agy.cmd'),
        (Join-Path $HOME '.gemini\bin\agy.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Antigravity\bin\agy.exe'),
        (Join-Path $env:APPDATA 'npm\agy.cmd')
    )
    foreach ($cand in $agyCandidates) {
        if ($cand -and (Test-Path $cand)) { $agyTarget = $cand; break }
    }
    if ($agyTarget -and -not (Test-Path (Join-Path $binDir 'agy.cmd'))) {
        $shimContent = "@echo off`r`n`"$agyTarget`" %*`r`nexit /b %errorlevel%`r`n"
        [System.IO.File]::WriteAllText((Join-Path $binDir 'agy.cmd'), $shimContent)
    }

    # codex detection
    $codexTarget = $null
    $codexCandidates = @(
        (Join-Path $HOME '.codex\plugins\.plugin-appserver\codex.exe'),
        (Join-Path $env:APPDATA 'npm\codex.cmd'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Codex\codex.exe')
    )
    foreach ($cand in $codexCandidates) {
        if ($cand -and (Test-Path $cand)) { $codexTarget = $cand; break }
    }
    if ($codexTarget -and -not (Test-Path (Join-Path $binDir 'codex.cmd'))) {
        $shimContent = "@echo off`r`n`"$codexTarget`" %*`r`nexit /b %errorlevel%`r`n"
        [System.IO.File]::WriteAllText((Join-Path $binDir 'codex.cmd'), $shimContent)
    }
}

# 4. Completion message
Write-Host "Setup complete!"
