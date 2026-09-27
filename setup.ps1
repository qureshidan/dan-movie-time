$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) { throw 'Install Python 3.11 or newer and enable Add Python to PATH.' }
& $pythonCommand.Source -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Setup complete. Double-click Start Movie Time.cmd.'
