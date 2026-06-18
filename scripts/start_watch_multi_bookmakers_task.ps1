$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Projetos\Surebet"
$OutputDir = Join-Path $ProjectRoot "outputs"
$LogPath = Join-Path $OutputDir "watch_multi_bookmakers_7200.log"
$TaskName = "SurebetWatchMultiBookmakers"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Write-WatchLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "$timestamp | task-start | $Message"
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    throw "Scheduled task '$TaskName' does not exist. Run scripts\register_watch_multi_bookmakers_task.ps1 first."
}

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$task = Get-ScheduledTask -TaskName $TaskName
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName

Write-WatchLog "requested scheduled task start; state=$($task.State); last_result=$($taskInfo.LastTaskResult)"

[pscustomobject]@{
    TaskName = $TaskName
    ScheduledTaskState = $task.State
    LastRunTime = $taskInfo.LastRunTime
    LastTaskResult = $taskInfo.LastTaskResult
    NextRunTime = $taskInfo.NextRunTime
    LogPath = $LogPath
}
