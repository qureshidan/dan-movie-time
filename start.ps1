$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Run setup.ps1 first.'
}
try {
    $runningStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/status' -TimeoutSec 2
    if ($runningStatus.paired) {
        Write-Host 'Movie Time is already running. Open http://127.0.0.1:8765'
        Write-Host 'Choose Connect a TV on that page for the address and pairing code.'
        exit 0
    }
} catch { }
& $pythonPath app.py
