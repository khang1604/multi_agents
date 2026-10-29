# Add only this Hub directory to the current user's PATH; no administrator needed.
$ErrorActionPreference = 'Stop'
$hubRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'bin'
if (-not (Test-Path -LiteralPath (Join-Path $hubRoot 'hub.cmd'))) {
    throw 'bin/hub.cmd not found.'
}
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$entries = @($userPath -split ';' | Where-Object { $_ })
if ($entries -notcontains $hubRoot) {
    $newPath = (@($entries) + $hubRoot) -join ';'
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
}
if (($env:Path -split ';') -notcontains $hubRoot) {
    $env:Path = "$hubRoot;$env:Path"
}
Write-Host "Installed hub command for current user: $hubRoot"
Write-Host 'Open a new CMD/PowerShell terminal, enter a project and run: hub here'
Write-Host 'If another hub command exists, use hub.cmd or the full path to this hub.cmd.'
