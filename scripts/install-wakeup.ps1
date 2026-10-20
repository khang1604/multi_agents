param(
    [Parameter(Mandatory=$true)][string]$TaskName,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$HubHome,
    [switch]$Owned
)
$ErrorActionPreference = 'Stop'
if ($TaskName -notmatch '^MultiAgents-Wake-[a-f0-9]{12}$') { throw 'Invalid owned task name' }
foreach ($taskPath in @($PythonPath, $SourcePath, $HubHome)) {
    if ($taskPath.Contains('"') -or $taskPath.Contains("`r") -or $taskPath.Contains("`n")) { throw 'Invalid runtime path' }
}
$taskArguments = '"' + (Join-Path $SourcePath 'ma.py') + '" --home "' + $HubHome + '" wake'
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    if (-not $Owned -or $existing.Actions.Count -ne 1 -or $existing.Actions[0].Execute -ne $PythonPath -or $existing.Actions[0].Arguments -ne $taskArguments) {
        throw 'Existing task is unowned or changed; preserved'
    }
    Write-Output 'Owned wake task already configured'
    exit 0
}
$action = New-ScheduledTaskAction -Execute $PythonPath -Argument $taskArguments -WorkingDirectory $SourcePath
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Wake the owned Multi Agents queue; no direct model calls or budget changes.' | Out-Null
Write-Output 'Owned wake task registered'
