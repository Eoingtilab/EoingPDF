param([switch]$UseSilentScript)
$ErrorActionPreference = 'Stop'
$projectFolder = Split-Path $PSScriptRoot -Parent
Set-Location $projectFolder
$version = (Get-Content VERSION -Raw).Trim()
$installer = Join-Path $projectFolder "release\EoingPDF-$version-Setup-x64.exe"
$testFolder = Join-Path $projectFolder 'temp\installer-smoke'
$appFolder = Join-Path $testFolder 'app'
$licenseFolder = Join-Path $testFolder 'localappdata\EoingPDF\license'
$pythonExe = Join-Path $projectFolder '.venv_d\Scripts\python.exe'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{2F0A1255-6F4C-44E4-9088-35393E2E0B35}_is1'
$previousLocalAppData = $env:LOCALAPPDATA
$previousQtPlatform = $env:QT_QPA_PLATFORM
$originalFailure = $null
$cleanupFailures = [System.Collections.Generic.List[string]]::new()
$portableExe = Join-Path $projectFolder 'release\EoingPDF\EoingPDF.exe'
$commandKey = 'HKCU:\Software\Classes\EoingPDF.Document\shell\open\command'
$originalCommand = if (Test-Path $commandKey) { (Get-Item $commandKey).GetValue('') } else { $null }
$restorePortable = $originalCommand -eq ('"' + $portableExe + '" "%1"')
if ($originalCommand -and -not $restorePortable) { throw '다른 어잉PDF의 연결이 있어 자동 설치 테스트를 중단합니다.' }

function Invoke-TestProcess {
    param([string]$Executable, [string[]]$Arguments, [int]$TimeoutSeconds = 120)
    $ownedProcess = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        while (-not $ownedProcess.WaitForExit(1000)) {
            if ([DateTime]::UtcNow -ge $deadline) {
                # Stop only the exact process created by this test.
                $ownedProcess.Kill()
                $null = $ownedProcess.WaitForExit(5000)
                throw "테스트 프로세스 시간 초과: $Executable (PID $($ownedProcess.Id))"
            }
        }
        if ($ownedProcess.ExitCode -ne 0) {
            throw "테스트 프로세스 실패: $Executable (종료 코드 $($ownedProcess.ExitCode))"
        }
    } finally {
        $ownedProcess.Dispose()
    }
}
if (Test-Path $uninstallKey) { throw '기존 설치형 앱이 있어 자동 설치 테스트를 중단합니다.' }
New-Item -ItemType Directory -Path $testFolder -Force | Out-Null
try {
    foreach ($pass in 1..2) {
        $setupArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/DIR="' + $appFolder + '"'), ('/LOG="' + (Join-Path $testFolder "install-$pass.log") + '"'))
        if ($UseSilentScript -and $pass -eq 1) {
            $wrapper = Join-Path $projectFolder 'release\install-silent.cmd'
            if (-not (Test-Path -LiteralPath $wrapper)) { throw '무인 설치 스크립트가 없습니다.' }
            $commandArguments = '""{0}" /S /DIR="{1}" /LOG="{2}""' -f $wrapper, $appFolder, (Join-Path $testFolder 'silent-wrapper.log')
            Invoke-TestProcess $env:ComSpec @('/d', '/s', '/c', $commandArguments)
        } else {
            Invoke-TestProcess $installer $setupArgs
        }
        if ((Get-Content (Join-Path $appFolder 'VERSION') -Raw).Trim() -ne $version) { throw '설치 버전 불일치' }
        $command = (Get-Item 'HKCU:\Software\Classes\EoingPDF.Document\shell\open\command').GetValue('')
        if ($command -ne ('"' + (Join-Path $appFolder 'EoingPDF.exe') + '" "%1"')) { throw 'PDF 실행 연결 불일치' }
        $icon = (Get-Item 'HKCU:\Software\Classes\EoingPDF.Document\DefaultIcon').GetValue('')
        if ($icon -notlike '*installer-smoke*pdf_icon.ico*') { throw 'PDF 아이콘 불일치' }
        if (-not (Test-Path $uninstallKey)) { throw '제거 등록 누락' }
    }
    # Uninstall must preserve files that were not supplied by the installer.
    Set-Content -LiteralPath (Join-Path $appFolder 'user-file.txt') -Value 'preserve me'
    if (-not (Test-Path $pythonExe)) { throw '테스트용 Python 환경이 없습니다.' }
    New-Item -ItemType Directory -Path $licenseFolder -Force | Out-Null
    & $pythonExe (Join-Path $projectFolder 'tests\seed_test_license.py') $licenseFolder
    if ($LASTEXITCODE -ne 0) { throw '격리된 테스트 라이선스 생성 실패' }
    $env:LOCALAPPDATA = Join-Path $testFolder 'localappdata'
    $env:QT_QPA_PLATFORM = 'offscreen'
    $screenshot = Join-Path $testFolder 'installed-viewer.png'
    if (Test-Path -LiteralPath $screenshot) { Remove-Item -LiteralPath $screenshot }
    Invoke-TestProcess (Join-Path $appFolder 'EoingPDF.exe') @('"' + (Join-Path $projectFolder 'temp\viewer-test\원본.pdf') + '"', '--screenshot', '"' + $screenshot + '"')
    if (-not (Test-Path -LiteralPath $screenshot)) { throw '설치된 뷰어 실행 실패' }
} catch {
    $originalFailure = $_
} finally {
    if ($null -eq $previousQtPlatform) { Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue }
    else { $env:QT_QPA_PLATFORM = $previousQtPlatform }
    if ($null -eq $previousLocalAppData) { Remove-Item Env:\LOCALAPPDATA -ErrorAction SilentlyContinue }
    else { $env:LOCALAPPDATA = $previousLocalAppData }
    $uninstaller = Join-Path $appFolder 'unins000.exe'
    if (Test-Path $uninstaller) {
        try { Invoke-TestProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') }
        catch { $cleanupFailures.Add($_.ToString()) }
    }
    if ($restorePortable) {
        try { Invoke-TestProcess $portableExe @('--register-shell') }
        catch { $cleanupFailures.Add($_.ToString()) }
    }
}
if ($originalFailure -or $cleanupFailures.Count) {
    $details = @()
    if ($originalFailure) { $details += '최초 실패: ' + $originalFailure.ToString() }
    $details += $cleanupFailures | ForEach-Object { '정리/복원 실패: ' + $_ }
    throw ($details -join [Environment]::NewLine)
}
if (Test-Path $uninstallKey) { throw '제거 등록이 남았습니다.' }
if (Test-Path (Join-Path $appFolder 'EoingPDF.exe')) { throw '프로그램 제거 실패' }
if (-not (Test-Path (Join-Path $appFolder 'user-file.txt'))) { throw '사용자 파일이 제거되었습니다.' }
Write-Output 'PASS: install, upgrade, shell registration, installed viewer, uninstall and user-file preservation'
if ($UseSilentScript) { Write-Output 'PASS: /S deployment wrapper used the real installer' }
