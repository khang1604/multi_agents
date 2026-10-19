# Optional: current-user Windows logon task. No administrator account required.
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$HubHome = Join-Path $Root 'data'
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = (& py -3 -c 'import sys; print(sys.executable)').Trim()
} else {
    $Python = (& python -c 'import sys; print(sys.executable)').Trim()
}
if (-not (Test-Path $Python)) { throw 'Không tìm thấy Python. Cài Python 3.11+ rồi thử lại.' }
$Entry = Join-Path $Root 'hub.py'
& $Python $Entry --home $HubHome init
if ($LASTEXITCODE -ne 0) { throw 'Khởi tạo thất bại.' }
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}" --home "{1}" daemon' -f $Entry, $HubHome) -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $Identity
$Principal = New-ScheduledTaskPrincipal -UserId $Identity -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'AgentHubPrivate' -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description 'Local personal agent queue; resumes saved workflows within their budgets.' -Force | Out-Null
Write-Host 'Đã cài task AgentHubPrivate chạy khi bạn đăng nhập Windows. Chạy hub.py start để bật ngay.'
