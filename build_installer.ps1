param([string]$Compiler = "$PSScriptRoot\build\tools\InnoSetup\ISCC.exe")
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath $Compiler)) { throw 'Inno Setup 6 컴파일러 경로를 -Compiler로 지정해 주세요.' }
$version = (Get-Content VERSION -Raw).Trim()
$packagedVersion = (Get-Content release/EoingPDF/VERSION -Raw).Trim()
if ($version -ne $packagedVersion) { throw 'build_release.ps1로 최신 프로그램을 먼저 빌드해 주세요.' }
& $Compiler packaging/setup.iss
if ($LASTEXITCODE -ne 0) { throw '설치 파일 빌드 실패' }
Get-FileHash -LiteralPath "release/EoingPDF-$version-Setup-x64.exe" -Algorithm SHA256
