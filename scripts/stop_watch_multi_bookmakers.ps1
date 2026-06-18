$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Projetos\Surebet"
$OutputDir = Join-Path $ProjectRoot "outputs"
$LogPath = Join-Path $OutputDir "watch_multi_bookmakers_7200.log"
$PidPath = Join-Path $OutputDir "watch_multi_bookmakers.pid"
$TaskName = "SurebetWatchMultiBookmakers"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Write-WatchLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "$timestamp | task-stop | $Message"
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task -and $task.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-WatchLog "requested scheduled task stop; task=$TaskName"
}

$processes = @(Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and
        (
            ($_.CommandLine -match "main\.py" -and $_.CommandLine -match "watch-multi-bookmakers") -or
            ($_.CommandLine -match "start_watch_multi_bookmakers\.ps1")
        )
    })

$allProcesses = @(Get-CimInstance Win32_Process)
$processIds = New-Object System.Collections.Generic.HashSet[int]
foreach ($process in $processes) {
    [void]$processIds.Add([int]$process.ProcessId)
}

$changed = $true
while ($changed) {
    $changed = $false
    foreach ($process in $allProcesses) {
        if ($processIds.Contains([int]$process.ParentProcessId) -and -not $processIds.Contains([int]$process.ProcessId)) {
            [void]$processIds.Add([int]$process.ProcessId)
            $changed = $true
        }
    }
}

foreach ($processId in $processIds) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $PidPath) {
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
}

Write-WatchLog "stopped remaining watch processes; count=$($processIds.Count)"

[pscustomobject]@{
    TaskName = $TaskName
    TaskStopped = [bool]$task
    StoppedProcessCount = $processIds.Count
    PidFileRemoved = -not (Test-Path -LiteralPath $PidPath)
}
