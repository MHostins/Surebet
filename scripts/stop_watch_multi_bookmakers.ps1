$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Projetos\Surebet"
$OutputDir = Join-Path $ProjectRoot "outputs"
$PidPath = Join-Path $OutputDir "watch_multi_bookmakers.pid"

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

"Stopped $($processIds.Count) watch-multi-bookmakers process(es)."
