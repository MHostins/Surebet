param(
    [int]$IntervalSeconds = 7200,
    [int]$MaxCycles = 0
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Projetos\Surebet"
$OutputDir = Join-Path $ProjectRoot "outputs"
$LogPath = Join-Path $OutputDir "watch_multi_bookmakers_7200.log"
$StdoutPath = Join-Path $OutputDir "watch_multi_bookmakers_stdout.log"
$StderrPath = Join-Path $OutputDir "watch_multi_bookmakers_stderr.log"
$PidPath = Join-Path $OutputDir "watch_multi_bookmakers.pid"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Write-WatchLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "$timestamp | launcher | $Message"
}

function Append-TextFileUtf8 {
    param(
        [string]$SourcePath,
        [string]$TargetPath,
        [string]$Prefix
    )
    if (-not (Test-Path -LiteralPath $SourcePath)) {
        return
    }
    $lines = Get-Content -LiteralPath $SourcePath -Encoding UTF8
    foreach ($line in $lines) {
        Add-Content -LiteralPath $TargetPath -Encoding UTF8 -Value "$Prefix$line"
    }
    Remove-Item -LiteralPath $SourcePath -Force -ErrorAction SilentlyContinue
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
    $StdoutTemp = Join-Path $OutputDir "watch_multi_bookmakers_stdout.tmp"
    $StderrTemp = Join-Path $OutputDir "watch_multi_bookmakers_stderr.tmp"
    Remove-Item -LiteralPath $StdoutTemp, $StderrTemp -Force -ErrorAction SilentlyContinue

    $process = Start-Process -FilePath "py" `
        -ArgumentList @("main.py", "--mode", "watch-multi-bookmakers") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $StdoutTemp `
        -RedirectStandardError $StderrTemp `
        -PassThru `
        -Wait
    $exitCode = $process.ExitCode
    Append-TextFileUtf8 -SourcePath $StdoutTemp -TargetPath $StdoutPath -Prefix ""
    Append-TextFileUtf8 -SourcePath $StderrTemp -TargetPath $StderrPath -Prefix ""
    Write-WatchLog "watch exited; exit_code=$exitCode"
    exit $exitCode
}
catch {
    Append-TextFileUtf8 -SourcePath $StdoutTemp -TargetPath $StdoutPath -Prefix ""
    Append-TextFileUtf8 -SourcePath $StderrTemp -TargetPath $StderrPath -Prefix ""
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
