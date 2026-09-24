"""Exercise the smoke driver's error cleanup without touching Windows registration."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r'''
$env:LOCALAPPDATA = 'original-localappdata-sentinel'
$env:QT_QPA_PLATFORM = 'original-qt-sentinel'
$script:launchCount = 0
function Test-Path {
    param([string]$Path, [string]$LiteralPath)
    $candidate = if ($LiteralPath) { $LiteralPath } else { $Path }
    if ($candidate -like 'HKCU:*') { return $false }
    if ($candidate.EndsWith('unins000.exe')) { return $env:TEST_CLEANUP_FAILURE -eq '1' }
    return Microsoft.PowerShell.Management\Test-Path -LiteralPath $candidate
}
function Start-Process {
    $script:launchCount++
    if ($script:launchCount -eq 1) { throw 'injected primary installation failure' }
    throw 'injected cleanup failure'
}
$caught = $null
try { & (Join-Path $env:EOING_TEST_PROJECT 'tests/installer_smoke.ps1') }
catch { $caught = $_.ToString() }
if (-not $caught.Contains('injected primary installation failure')) { throw 'Original error lost' }
if ($env:TEST_CLEANUP_FAILURE -eq '1' -and -not $caught.Contains('injected cleanup failure')) {
    throw 'Cleanup error lost'
}
if ($env:LOCALAPPDATA -ne 'original-localappdata-sentinel') { throw 'LOCALAPPDATA was corrupted' }
if ($env:QT_QPA_PLATFORM -ne 'original-qt-sentinel') { throw 'QT_QPA_PLATFORM was corrupted' }
Write-Output 'PASS: original failure and environment preserved'
'''


@pytest.mark.parametrize('cleanup_failure', ['0', '1'])
def test_early_failure_preserves_environment_and_first_error(cleanup_failure):
    powershell = shutil.which('pwsh') or shutil.which('powershell')
    if powershell is None:
        pytest.skip('PowerShell is required')
    env = dict(os.environ, EOING_TEST_PROJECT=str(ROOT), TEST_CLEANUP_FAILURE=cleanup_failure)
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', SCRIPT],
                            env=env, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert b'PASS: original failure and environment preserved' in result.stdout
