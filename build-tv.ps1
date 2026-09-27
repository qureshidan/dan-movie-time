param(
    [string]$SdkPath = "$env:LOCALAPPDATA\Android\Sdk",
    [string]$JavaPath = $env:JAVA_HOME
)
$ErrorActionPreference = 'Stop'
if (-not $JavaPath -or -not (Test-Path (Join-Path $JavaPath 'bin\javac.exe'))) { throw 'Set JAVA_HOME to a JDK directory, or pass -JavaPath.' }
Set-Location -LiteralPath $PSScriptRoot
$buildPath = Join-Path $PSScriptRoot 'android\build'
$toolsPath = Join-Path $SdkPath 'build-tools\36.1.0'
$platformPath = Join-Path $SdkPath 'platforms\android-36.1\android.jar'
$env:JAVA_HOME = $JavaPath
$env:PATH = (Join-Path $JavaPath 'bin') + ';' + $env:PATH
New-Item -ItemType Directory -Force -Path $buildPath,(Join-Path $buildPath 'classes'),(Join-Path $buildPath 'dex'),(Join-Path $PSScriptRoot 'dist'),(Join-Path $PSScriptRoot 'private') | Out-Null
function Check-Build { if ($LASTEXITCODE -ne 0) { throw 'TV app build failed. See the command output above.' } }
& (Join-Path $toolsPath 'aapt2.exe') compile --dir android/res -o "$buildPath\resources.zip"
Check-Build
& (Join-Path $toolsPath 'aapt2.exe') link -o "$buildPath\unsigned.apk" --manifest android/AndroidManifest.xml -I $platformPath "$buildPath\resources.zip"
Check-Build
& (Join-Path $JavaPath 'bin\javac.exe') -encoding UTF-8 -source 8 -target 8 -classpath $platformPath -d "$buildPath\classes" android/src/home/movietime/tv/MainActivity.java
Check-Build
$classFiles = @(Get-ChildItem -LiteralPath "$buildPath\classes" -Recurse -Filter '*.class' | ForEach-Object FullName)
& (Join-Path $toolsPath 'd8.bat') --lib $platformPath --min-api 23 --output "$buildPath\dex" @classFiles
Check-Build
& (Join-Path $JavaPath 'bin\jar.exe') uf "$buildPath\unsigned.apk" -C "$buildPath\dex" classes.dex
Check-Build
& (Join-Path $toolsPath 'zipalign.exe') -f 4 "$buildPath\unsigned.apk" "$buildPath\aligned.apk"
Check-Build
$keyPath = Join-Path $PSScriptRoot 'private\tv-signing.p12'
$passwordPath = Join-Path $PSScriptRoot 'private\tv-signing-password.txt'
if (-not (Test-Path -LiteralPath $keyPath)) {
    $keyPassword = [Guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText($passwordPath, $keyPassword)
    & (Join-Path $JavaPath 'bin\keytool.exe') -genkeypair -keystore $keyPath -storepass:file $passwordPath -alias movietime -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Movie Time Personal App' -storetype PKCS12
    Check-Build
}
& (Join-Path $toolsPath 'apksigner.bat') sign --ks $keyPath --ks-pass "file:$passwordPath" --out dist/Movie-Time-TV.apk "$buildPath\aligned.apk"
Check-Build
& (Join-Path $toolsPath 'apksigner.bat') verify dist/Movie-Time-TV.apk
Check-Build
Get-Item -LiteralPath dist/Movie-Time-TV.apk | Select-Object Name,Length
