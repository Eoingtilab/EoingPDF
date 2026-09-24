$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv_d\Scripts\python.exe'
$version = (Get-Content VERSION -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION 형식이 올바르지 않습니다.' }
& $pythonExe -m pyflakes src main.py scripts
if ($LASTEXITCODE -ne 0) { throw '정적 검사 실패' }
& $pythonExe scripts\package_search_model.py --verify
if ($LASTEXITCODE -ne 0) { throw '검색 모델 무결성 검사 실패' }
New-Item -ItemType Directory -Path build\portable-tools -Force | Out-Null
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /target:winexe /platform:x64 /out:build\portable-tools\EoingPDF.Shell.exe /reference:System.Windows.Forms.dll native\ShellBridge.cs
if ($LASTEXITCODE -ne 0) { throw '포터블 셸 도우미 빌드 실패' }
$previousOnefile = $env:EOINGPDF_BUILD_ONEFILE
try {
    $env:EOINGPDF_BUILD_ONEFILE = '1'
    & $pythonExe -m PyInstaller --noconfirm --distpath build\portable-staging --workpath build\portable packaging\EoingPDF.spec
    if ($LASTEXITCODE -ne 0) { throw '단일 실행파일 패키징 실패' }
} finally {
    if ($null -eq $previousOnefile) { Remove-Item Env:\EOINGPDF_BUILD_ONEFILE -ErrorAction SilentlyContinue }
    else { $env:EOINGPDF_BUILD_ONEFILE = $previousOnefile }
}
$portable = Join-Path $PSScriptRoot "build\portable-staging\EoingPDF-$version-portable.exe"
& $pythonExe tests\portable_smoke.py --exe $portable
if ($LASTEXITCODE -ne 0) { throw '단일 실행파일 검증 실패' }
& $pythonExe tests\frozen_localization_smoke.py --exe $portable
if ($LASTEXITCODE -ne 0) { throw '단일 실행파일 다국어 검증 실패' }
& $pythonExe tests\portable_update_smoke.py --exe $portable
if ($LASTEXITCODE -ne 0) { throw '단일 실행파일 교체 및 복원 검증 실패' }
Copy-Item -LiteralPath $portable -Destination (Join-Path $PSScriptRoot "release\EoingPDF-$version-portable.exe")
Get-FileHash -LiteralPath "release\EoingPDF-$version-portable.exe" -Algorithm SHA256 | Format-List
