$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$releaseFolder = Join-Path $PSScriptRoot 'release\EoingPDF'
$releaseFolder = Join-Path $PSScriptRoot 'release\EoingPDF'
New-Item -ItemType Directory -Force -Path (Split-Path $releaseFolder -Parent) | Out-Null
$running = Get-Process EoingPDF -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $releaseFolder 'EoingPDF.exe') }
if ($running) { throw '배포 폴더의 어잉PDF를 종료한 뒤 다시 빌드해 주세요.' }
$pythonExe = Join-Path $PSScriptRoot '.venv_d\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { $pythonExe = 'python' }
& $pythonExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw '테스트 실패' }
if (-not $env:EOING_SKIP_NATIVE) {
    & .\native\build_hwp.cmd
    if ($LASTEXITCODE -ne 0) { throw '한글 접근 모듈 빌드 실패' }
}
& $pythonExe scripts\make_icon.py
if ($LASTEXITCODE -ne 0) { throw '아이콘 생성 실패' }
& $pythonExe -m PyInstaller --noconfirm --distpath build\staging --workpath build packaging\EoingPDF.spec
if ($LASTEXITCODE -ne 0) { throw '패키징 실패' }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /target:winexe /platform:x64 /out:build\staging\EoingPDF\EoingPDF.Shell.exe /reference:System.Windows.Forms.dll native\ShellBridge.cs
if ($LASTEXITCODE -ne 0) { throw '우클릭 연결 프로그램 빌드 실패' }
Copy-Item README.md,CHANGELOG.md,VERSION,docs\THIRD_PARTY.md -Destination build\staging\EoingPDF
Copy-Item docs -Destination build\staging\EoingPDF -Recurse
Copy-Item install-context-menu.cmd,uninstall-context-menu.cmd -Destination build\staging\EoingPDF
# Keep the preceding package until the complete replacement has been built.
$previousFolder = Join-Path $PSScriptRoot ('build\previous-release-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path $releaseFolder) { Move-Item -LiteralPath $releaseFolder -Destination $previousFolder }
try { Move-Item -LiteralPath (Join-Path $PSScriptRoot 'build\staging\EoingPDF') -Destination $releaseFolder }
catch {
    if (Test-Path $previousFolder) { Move-Item -LiteralPath $previousFolder -Destination $releaseFolder }
    throw
}
Compress-Archive -Path release\EoingPDF -DestinationPath release\EoingPDF-2.0-portable.zip -Force
& $pythonExe scripts\package_source.py
if ($LASTEXITCODE -ne 0) { throw '소스 패키징 실패' }
Get-FileHash release\EoingPDF-2.0-portable.zip -Algorithm SHA256 | Format-List
