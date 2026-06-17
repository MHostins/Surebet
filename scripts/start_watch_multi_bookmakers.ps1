param(
    [int]$IntervalSeconds = 7200,
    [int]$MaxCycles = 0
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Projetos\Surebet"
$OutputDir = Join-Path $ProjectRoot "outputs"
$LogPath = Join-Path $OutputDir "watch_multi_bookmakers_7200.log"
$PidPath = Join-Path $OutputDir "watch_multi_bookmakers.pid"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Write-WatchLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "$timestamp | launcher | $Message"
}

$currentPid = $PID
$existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.ProcessId -ne $currentPid -and
        $_.CommandLine -and
        (
            ($_.CommandLine -match "main\.py" -and $_.CommandLine -match "watch-multi-bookmakers") -or
            ($_.CommandLine -match "start_watch_multi_bookmakers\.ps1")
        )
    } |
    Select-Object -First 1

if ($existing) {
    Write-WatchLog "watch already running; pid=$($existing.ProcessId); command=$($existing.CommandLine)"
    Set-Content -LiteralPath $PidPath -Value $existing.ProcessId
    exit 0
}

Set-Location -LiteralPath $ProjectRoot
$env:WATCH_MULTI_BOOKMAKER_INTERVAL_SECONDS = [string]$IntervalSeconds
$env:WATCH_MULTI_BOOKMAKER_MAX_CYCLES = [string]$MaxCycles

Write-WatchLog "starting watch-multi-bookmakers; interval=$IntervalSeconds; max_cycles=$MaxCycles"
Set-Content -LiteralPath $PidPath -Value $currentPid

try {
    $StdoutPath = Join-Path $OutputDir "watch_multi_bookmakers_stdout.log"
    $StderrPath = Join-Path $OutputDir "watch_multi_bookmakers_stderr.log"
    $process = Start-Process -FilePath "py" `
        -ArgumentList @("main.py", "--mode", "watch-multi-bookmakers") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -PassThru `
        -Wait
    $exitCode = $process.ExitCode
    Write-WatchLog "watch exited; exit_code=$exitCode"
    exit $exitCode
}
catch {
    Write-WatchLog "watch failed; error=$($_.Exception.Message)"
    throw
}
finally {
    if (Test-Path -LiteralPath $PidPath) {
        $recordedPid = Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue
        if ($recordedPid -eq [string]$currentPid) {
            Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        }
    }
}
