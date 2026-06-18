param(
    [int]$IntervalSeconds = 7200,
    [int]$MaxCycles = 0
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Projetos\Surebet"
$OutputDir = Join-Path $ProjectRoot "outputs"
$LogPath = Join-Path $OutputDir "watch_multi_bookmakers_7200.log"
$TaskName = "SurebetWatchMultiBookmakers"
$StartScriptPath = Join-Path $ProjectRoot "scripts\start_watch_multi_bookmakers.ps1"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Write-WatchLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "$timestamp | task-register | $Message"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScriptPath`" -IntervalSeconds $IntervalSeconds -MaxCycles $MaxCycles" `
    -WorkingDirectory $ProjectRoot

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable:$false

$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Limited

$task = New-ScheduledTask `
    -Action $action `
    -Settings $settings `
    -Principal $principal `
    -Description "Runs Surebet watch-multi-bookmakers on demand only. No automatic logon trigger."

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $task `
    -Force | Out-Null

Write-WatchLog "registered scheduled task; task=$TaskName; interval=$IntervalSeconds; max_cycles=$MaxCycles; triggers=none"

[pscustomobject]@{
    TaskName = $TaskName
    Registered = $true
    Triggers = "none"
    IntervalSeconds = $IntervalSeconds
    MaxCycles = $MaxCycles
    Action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$StartScriptPath`" -IntervalSeconds $IntervalSeconds -MaxCycles $MaxCycles"
    WorkingDirectory = $ProjectRoot
    LogPath = $LogPath
}
