# Optional: current-user Windows logon task. No administrator account required.
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$HubHome = Join-Path $Root 'data'
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = (& py -3 -c 'import sys; print(sys.executable)').Trim()
} else {
    $Python = (& python -c 'import sys; print(sys.executable)').Trim()
}
if (-not (Test-Path $Python)) { throw 'Python not found. Install Python 3.11+ and retry.' }
$Entry = Join-Path $Root 'cli/hub.py'
& $Python $Entry --home $HubHome init
if ($LASTEXITCODE -ne 0) { throw 'Initialization failed.' }
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}" --home "{1}" daemon' -f $Entry, $HubHome) -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $Identity
$Principal = New-ScheduledTaskPrincipal -UserId $Identity -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'AgentHubPrivate' -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description 'Local personal agent queue; resumes saved workflows within their budgets.' -Force | Out-Null
Write-Host 'Installed the AgentHubPrivate task to run at Windows login. Run python cli/hub.py start to start it now.'
