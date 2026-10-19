$ErrorActionPreference = 'Stop'
Unregister-ScheduledTask -TaskName 'AgentHubPrivate' -Confirm:$false -ErrorAction SilentlyContinue
Write-Host 'Đã gỡ autostart. Để dừng phiên đang chạy, dùng hub.py stop.'
