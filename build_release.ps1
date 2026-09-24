$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$version = (Get-Content VERSION -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION 형식을 확인해 주세요.' }
$releaseFolder = Join-Path $PSScriptRoot 'release\EoingPDF'
$releaseFolder = Join-Path $PSScriptRoot 'release\EoingPDF'
New-Item -ItemType Directory -Force -Path (Split-Path $releaseFolder -Parent) | Out-Null
$running = Get-Process EoingPDF -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $releaseFolder 'EoingPDF.exe') }
if ($running) { throw '배포 폴더의 어잉PDF를 종료한 뒤 다시 빌드해 주세요.' }
$pythonExe = Join-Path $PSScriptRoot '.venv_d\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { $pythonExe = 'python' }
& $pythonExe -m pyflakes src main.py scripts
if ($LASTEXITCODE -ne 0) { throw '정적 코드 검사 실패' }
& $pythonExe scripts\package_search_model.py --verify
if ($LASTEXITCODE -ne 0) { throw '검색 모델 파일 검증 실패' }
& .\native\build_ink.cmd
if ($LASTEXITCODE -ne 0) { throw 'Direct2D 판서 빌드 실패' }
& .\native\build_explorer.cmd
if ($LASTEXITCODE -ne 0) { throw '현대식 탐색기 명령 빌드 실패' }
& $pythonExe scripts\package_modern_shell.py
if ($LASTEXITCODE -ne 0) { throw '현대식 탐색기 앱 ID 패키지 생성 실패' }
$testFiles = @(Get-ChildItem tests -Filter 'test_*.py' | Sort-Object Name | ForEach-Object FullName)
$previousQtPlatform = $env:QT_QPA_PLATFORM
$testRunFolder = Join-Path $PSScriptRoot ('temp\release-tests-' + [guid]::NewGuid().ToString('N'))
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $pythonExe -m pytest $testFiles -q -p no:cacheprovider "--basetemp=$testRunFolder" --junitxml=temp/test-results/release-tests.xml
    if ($LASTEXITCODE -ne 0) { throw '통합 자동 검사 실패' }
} finally {
    $env:QT_QPA_PLATFORM = $previousQtPlatform
}
& $pythonExe tests\ui_regressions.py
if ($LASTEXITCODE -ne 0) { throw 'UI 회귀 테스트 실패' }
& $pythonExe tests\clipboard_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '표 선택/복사 UI 테스트 실패' }
& $pythonExe tests\diff_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '문서 비교 UI 테스트 실패' }
& $pythonExe tests\presenter_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '발표자 화면 UI 테스트 실패' }
& $pythonExe tests\native_ink_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw 'Windows GPU 판서 UI 테스트 실패' }
& $pythonExe tests\settings_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '설정 화면 UI 테스트 실패' }
& $pythonExe tests\theme_windows_smoke.py
if ($LASTEXITCODE -ne 0) { throw 'Windows 테마 및 DWM 통합 검사 실패' }
& $pythonExe tests\staging_dock_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '파일 모으기 드롭존 UI 검사 실패' }
& $pythonExe tests\localization_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '다국어 도구/양식/비교/발표 UI 검사 실패' }
& $pythonExe tests\license_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '라이선스 다국어 UI 테스트 실패' }
& $pythonExe tests\form_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '양식 입력 UI 테스트 실패' }
& $pythonExe tests\encrypted_viewer_smoke.py
if ($LASTEXITCODE -ne 0) { throw '암호 뷰어 테스트 실패' }
& $pythonExe tests\stamp_ui_smoke.py
if ($LASTEXITCODE -ne 0) { throw '도장 입력 UI 테스트 실패' }
& .\native\build_hwp.cmd
if ($LASTEXITCODE -ne 0) { throw '한글 접근 모듈 빌드 실패' }
& $pythonExe scripts\make_icon.py
if ($LASTEXITCODE -ne 0) { throw '아이콘 생성 실패' }
& $pythonExe -m PyInstaller --noconfirm --distpath build\staging --workpath build packaging\EoingPDF.spec
if ($LASTEXITCODE -ne 0) { throw '패키징 실패' }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /target:winexe /platform:x64 /out:build\staging\EoingPDF\EoingPDF.Shell.exe /reference:System.Windows.Forms.dll native\ShellBridge.cs
if ($LASTEXITCODE -ne 0) { throw '우클릭 연결 프로그램 빌드 실패' }
Copy-Item -LiteralPath assets\EoingPDF.Explorer.dll -Destination build\staging\EoingPDF\EoingPDF.Explorer.dll
Copy-Item README.md,CHANGELOG.md,VERSION,LICENSE,docs\THIRD_PARTY.md -Destination build\staging\EoingPDF
Copy-Item docs -Destination build\staging\EoingPDF -Recurse
Copy-Item install-context-menu.cmd,uninstall-context-menu.cmd -Destination build\staging\EoingPDF
& $pythonExe tests\frozen_smoke.py --exe build\staging\EoingPDF\EoingPDF.exe
if ($LASTEXITCODE -ne 0) { throw '패키징된 실행파일 기능 검사 실패' }
& $pythonExe tests\frozen_localization_smoke.py --exe build\staging\EoingPDF\EoingPDF.exe
if ($LASTEXITCODE -ne 0) { throw '패키징된 다국어 변환/검색/목차 검사 실패' }
& $pythonExe tests\frozen_update_smoke.py --folder build\staging\EoingPDF
if ($LASTEXITCODE -ne 0) { throw '패키징된 복구 도우미 검사 실패' }
# Keep the preceding package until the complete replacement has been built.
$previousFolder = Join-Path $PSScriptRoot ('build\previous-release-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
# Verify every directory moved below before recursive Windows directory moves.
$workspacePath = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\') + '\'
$stagingFolder = Join-Path $PSScriptRoot 'build\staging\EoingPDF'
foreach ($candidate in @($releaseFolder, $previousFolder, $stagingFolder)) {
    $resolvedCandidate = [IO.Path]::GetFullPath($candidate)
    if (-not $resolvedCandidate.StartsWith($workspacePath, [StringComparison]::OrdinalIgnoreCase)) { throw '빌드 이동 경로가 프로젝트 밖입니다.' }
    $ancestor = $resolvedCandidate
    while ($ancestor.Length -ge $workspacePath.Length) {
        if (Test-Path -LiteralPath $ancestor) {
            if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '빌드 이동 경로에 재분석 지점이 있습니다.' }
        }
        $ancestor = Split-Path -Parent $ancestor
    }
}
if (Test-Path $releaseFolder) { Move-Item -LiteralPath $releaseFolder -Destination $previousFolder }
try { Move-Item -LiteralPath $stagingFolder -Destination $releaseFolder }
catch {
    if (Test-Path $previousFolder) { Move-Item -LiteralPath $previousFolder -Destination $releaseFolder }
    throw
}
$iscc = Join-Path $PSScriptRoot 'build\tools\InnoSetup\ISCC.exe'
if (-not (Test-Path $iscc)) { throw 'Inno Setup 컴파일러가 없습니다. build/tools/InnoSetup/ISCC.exe를 준비해 주세요.' }
& $iscc /Qp (Join-Path $PSScriptRoot 'packaging\setup.iss')
if ($LASTEXITCODE -ne 0) { throw '설치파일 컴파일 실패' }
$installerPath = Join-Path $PSScriptRoot "release\EoingPDF-$version-Setup-x64.exe"
if (-not (Test-Path $installerPath) -or (Get-Item $installerPath).Length -lt 1MB) { throw '설치파일 산출물이 없거나 너무 작습니다.' }
Copy-Item -LiteralPath packaging\install-silent.cmd -Destination release\install-silent.cmd
Compress-Archive -Path release\EoingPDF -DestinationPath "release\EoingPDF-$version-portable.zip" -Force
& $pythonExe scripts\package_source.py
if ($LASTEXITCODE -ne 0) { throw '소스 패키징 실패' }
& $pythonExe tests\source_package_smoke.py
if ($LASTEXITCODE -ne 0) { throw '소스 ZIP 검증 실패' }
Get-FileHash "release\EoingPDF-$version-portable.zip" -Algorithm SHA256 | Format-List
