$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Projetos\Surebet"
$OutputDir = Join-Path $ProjectRoot "outputs"
$LogPath = Join-Path $OutputDir "watch_multi_bookmakers_7200.log"
$StdoutPath = Join-Path $OutputDir "watch_multi_bookmakers_stdout.log"
$StderrPath = Join-Path $OutputDir "watch_multi_bookmakers_stderr.log"
$HistoryPath = Join-Path $OutputDir "multi_bookmaker_watch_history.jsonl"
$UsageHistoryPath = Join-Path $OutputDir "the_odds_api_usage_history.jsonl"
$PidPath = Join-Path $OutputDir "watch_multi_bookmakers.pid"
$TaskName = "SurebetWatchMultiBookmakers"

$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and
        (
            ($_.CommandLine -match "main\.py" -and $_.CommandLine -match "watch-multi-bookmakers") -or
            ($_.CommandLine -match "start_watch_multi_bookmakers\.ps1")
        )
    } |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$taskInfo = if ($task) { Get-ScheduledTaskInfo -TaskName $TaskName } else { $null }

[pscustomobject]@{
    ProjectRoot = $ProjectRoot
    PidFile = if (Test-Path -LiteralPath $PidPath) { Get-Content -LiteralPath $PidPath } else { $null }
    RunningProcessCount = @($processes).Count
    Processes = $processes
    ScheduledTaskExists = [bool]$task
    ScheduledTaskState = if ($task) { $task.State } else { $null }
    LastTaskRunTime = if ($taskInfo) { $taskInfo.LastRunTime } else { $null }
    LastTaskResult = if ($taskInfo) { $taskInfo.LastTaskResult } else { $null }
    NextTaskRunTime = if ($taskInfo) { $taskInfo.NextRunTime } else { $null }
    LogPath = $LogPath
    UsageHistoryPath = $UsageHistoryPath
}

if (Test-Path -LiteralPath $LogPath) {
    "`n--- Last launcher log lines ---"
    Get-Content -LiteralPath $LogPath -Tail 30
}

if (Test-Path -LiteralPath $StderrPath) {
    "`n--- Last Python stderr log lines ---"
    Get-Content -LiteralPath $StderrPath -Tail 30
}

if (Test-Path -LiteralPath $StdoutPath) {
    "`n--- Last Python stdout log lines ---"
    Get-Content -LiteralPath $StdoutPath -Tail 30
}

if (Test-Path -LiteralPath $HistoryPath) {
    "`n--- Last watch history entries ---"
    Get-Content -LiteralPath $HistoryPath -Tail 5
}

if (Test-Path -LiteralPath $UsageHistoryPath) {
    "`n--- Last The Odds API usage entries ---"
    Get-Content -LiteralPath $UsageHistoryPath -Tail 5
}
