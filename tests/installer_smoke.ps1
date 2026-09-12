$ErrorActionPreference = 'Stop'
$projectFolder = Split-Path $PSScriptRoot -Parent
Set-Location $projectFolder
$version = (Get-Content VERSION -Raw).Trim()
$installer = Join-Path $projectFolder "release\EoingPDF-$version-Setup-x64.exe"
$testFolder = Join-Path $projectFolder 'temp\installer-smoke'
$appFolder = Join-Path $testFolder 'app'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{2F0A1255-6F4C-44E4-9088-35393E2E0B35}_is1'
if (Test-Path $uninstallKey) { throw '기존 설치형 앱이 있어 자동 설치 테스트를 중단합니다.' }
New-Item -ItemType Directory -Path $testFolder -Force | Out-Null
try {
    foreach ($pass in 1..2) {
        $setupArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/DIR="' + $appFolder + '"'), ('/LOG="' + (Join-Path $testFolder "install-$pass.log") + '"'))
        $setup = Start-Process -FilePath $installer -ArgumentList $setupArgs -WindowStyle Hidden -Wait -PassThru
        if ($setup.ExitCode -ne 0) { throw "설치 실패: $($setup.ExitCode)" }
        if ((Get-Content (Join-Path $appFolder 'VERSION') -Raw).Trim() -ne $version) { throw '설치 버전 불일치' }
        $command = (Get-Item 'HKCU:\Software\Classes\EoingPDF.Document\shell\open\command').GetValue('')
        if ($command -ne ('"' + (Join-Path $appFolder 'EoingPDF.exe') + '" "%1"')) { throw 'PDF 실행 연결 불일치' }
        $icon = (Get-Item 'HKCU:\Software\Classes\EoingPDF.Document\DefaultIcon').GetValue('')
        if ($icon -notlike '*installer-smoke*pdf_icon.ico*') { throw 'PDF 아이콘 불일치' }
        if (-not (Test-Path $uninstallKey)) { throw '제거 등록 누락' }
    }
    # Uninstall must preserve files that were not supplied by the installer.
    Set-Content -LiteralPath (Join-Path $appFolder 'user-file.txt') -Value 'preserve me'
    $env:QT_QPA_PLATFORM = 'offscreen'
    $reader = Start-Process -FilePath (Join-Path $appFolder 'EoingPDF.exe') -ArgumentList @('"' + (Join-Path $projectFolder 'temp\viewer-test\presentation.pdf') + '"', '--screenshot', '"' + (Join-Path $testFolder 'installed-viewer.png') + '"') -WindowStyle Hidden -Wait -PassThru
    if ($reader.ExitCode -ne 0 -or -not (Test-Path (Join-Path $testFolder 'installed-viewer.png'))) { throw '설치된 뷰어 실행 실패' }
    Write-Output 'PASS: install, upgrade, PDF command/icon registration, installed viewer launch'
} finally {
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    $uninstaller = Join-Path $appFolder 'unins000.exe'
    if (Test-Path $uninstaller) {
        $uninstall = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -WindowStyle Hidden -Wait -PassThru
        if ($uninstall.ExitCode -ne 0) { throw "제거 실패: $($uninstall.ExitCode)" }
    }
    $restore = Start-Process -FilePath (Join-Path $projectFolder 'release\EoingPDF\EoingPDF.exe') -ArgumentList '--register-shell' -WindowStyle Hidden -Wait -PassThru
    if ($restore.ExitCode -ne 0) { throw '기존 포터블 연결 복원 실패' }
}
if (Test-Path $uninstallKey) { throw '제거 등록이 남았습니다.' }
if (Test-Path (Join-Path $appFolder 'EoingPDF.exe')) { throw '프로그램 제거 실패' }
if (-not (Test-Path (Join-Path $appFolder 'user-file.txt'))) { throw '사용자 파일이 제거되었습니다.' }
Write-Output 'PASS: uninstall preserves user file, portable registration restored'
