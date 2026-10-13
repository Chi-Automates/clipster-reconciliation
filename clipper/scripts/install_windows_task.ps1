# Registers "Clipper Daily" in Task Scheduler: runs at 07:00 every day, and if the laptop
# was off or asleep at 07:00 it runs as soon as you next log in.
param([string]$At = "07:00")

$Script = Join-Path $PSScriptRoot "run_daily.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$Script`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask -TaskName "Clipper Daily" -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Clips Whop campaign footage and schedules posts via Post for Me" -Force | Out-Null
Write-Host "Registered 'Clipper Daily' at $At. Run it now with: Start-ScheduledTask -TaskName 'Clipper Daily'"
