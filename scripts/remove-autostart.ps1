$ErrorActionPreference = 'Stop'
Unregister-ScheduledTask -TaskName 'AgentHubPrivate' -Confirm:$false -ErrorAction SilentlyContinue
Write-Host 'Autostart removed. To stop the active session, use python cli/hub.py stop.'
