param([Parameter(Mandatory=$true)][string]$TvAddress)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$parsedAddress = $null
if (-not [Net.IPAddress]::TryParse($TvAddress,[ref]$parsedAddress) -or $parsedAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { throw 'Enter the IPv4 address shown on the TV.' }
$addressBytes = $parsedAddress.GetAddressBytes()
if (-not ($addressBytes[0] -eq 10 -or ($addressBytes[0] -eq 192 -and $addressBytes[1] -eq 168) -or ($addressBytes[0] -eq 172 -and $addressBytes[1] -ge 16 -and $addressBytes[1] -le 31))) { throw 'Use the local Wi-Fi address of your TV.' }
$adbPath = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
$deviceTarget = $TvAddress + ':5555'
& $adbPath connect $deviceTarget
Write-Host 'If the Fire Stick shows Allow USB debugging, approve this laptop on the TV.'
Read-Host 'Press Enter after approving the connection'
& $adbPath connect $deviceTarget
& $adbPath -s $deviceTarget get-state
if ($LASTEXITCODE -ne 0) { throw 'TV is not connected. Check ADB Debugging and approve the TV prompt.' }
& $adbPath -s $deviceTarget install -r '.\dist\Movie-Time-TV.apk'
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. See the message above.' }
& $adbPath -s $deviceTarget shell am start -n home.movietime.tv/.MainActivity
if ($LASTEXITCODE -ne 0) { throw 'The app was installed but could not launch.' }
