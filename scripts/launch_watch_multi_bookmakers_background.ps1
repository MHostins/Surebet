param(
    [int]$IntervalSeconds = 7200,
    [int]$MaxCycles = 0
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Projetos\Surebet"
$ScriptPath = Join-Path $ProjectRoot "scripts\start_watch_multi_bookmakers.ps1"

$process = Start-Process -FilePath "powershell.exe" `
    -WindowStyle Hidden `
    -PassThru `
    -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $ScriptPath,
        "-IntervalSeconds",
        [string]$IntervalSeconds,
        "-MaxCycles",
        [string]$MaxCycles
    )

"Started watch-multi-bookmakers launcher in background. Launcher PID: $($process.Id)"
"Use scripts\status_watch_multi_bookmakers.ps1 to inspect it."
"Use scripts\stop_watch_multi_bookmakers.ps1 to stop it."
