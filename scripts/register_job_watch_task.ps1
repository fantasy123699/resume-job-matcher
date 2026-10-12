param(
    [ValidatePattern("^([01]\d|2[0-3]):[0-5]\d$")]
    [string]$At = "11:00",
    [string]$TaskName = "ResumeJobMatcher-JobWatch"
)

$ErrorActionPreference = "Stop"
$Runner = Join-Path $PSScriptRoot "run_job_watch.ps1"
$Config = Join-Path (Split-Path -Parent $PSScriptRoot) "config/job_watch.local.json"

if (-not (Test-Path -LiteralPath $Config)) {
    throw "Missing $Config. Copy job_watch.example.json and customize the keywords first."
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Scheduled task '$TaskName' already exists. Remove or rename it explicitly before retrying."
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Daily approved-source campus recruitment keyword monitor"

Write-Host "Registered '$TaskName' to run every day at $At."
