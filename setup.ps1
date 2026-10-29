# Terminal-only setup. Does not change ExecutionPolicy or request Administrator.
$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot 'cli/ma.py'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $entry setup @args
} else {
    & python $entry setup @args
}
if ($LASTEXITCODE -ne 0) { throw 'Setup incomplete; inspect output. No security bypass is applied.' }
