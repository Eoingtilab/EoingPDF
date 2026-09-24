import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf import portable_update as portable
from eoingpdf.update_helper import read_status
from eoingpdf.update_snapshot import digest


@pytest.fixture
def prepared(tmp_path):
    target = tmp_path / '이름 바꾼 앱.exe'
    target.write_bytes(b'MZ' + b'old' * 1024)
    neighbor = tmp_path / 'user.pdf'
    neighbor.write_bytes(b'USER DOCUMENT')
    backup = portable.create(target, tmp_path / 'backups', '2.2.0')
    candidate = tmp_path / 'candidate.exe'
    candidate.write_bytes(b'MZ' + b'new' * 1024)
    return dict(kind='onefile', executable=str(target), backup=str(backup),
                installer=str(candidate), digest=digest(candidate), current_digest=digest(target),
                version='2.3.0', report=str(tmp_path / 'status.json'), restart=False)


@pytest.mark.parametrize('healthy', [True, False])
def test_verified_replace_or_restore_preserves_neighbors(prepared, monkeypatch, healthy):
    checks = []
    def probe(path, version):
        checks.append((path, version))
        return True if len(checks) == 1 else healthy
    monkeypatch.setattr(portable, 'runtime_healthy', probe)
    before = Path(prepared['executable']).read_bytes()
    assert portable.apply(prepared) == ('updated' if healthy else 'restored')
    target = Path(prepared['executable'])
    assert target.read_bytes() == (Path(prepared['installer']).read_bytes() if healthy else before)
    assert (target.parent / 'user.pdf').read_bytes() == b'USER DOCUMENT'
    assert (Path(prepared['backup']) / 'EoingPDF.exe').read_bytes() == before
    assert not list(target.parent.glob('.eoing-update-*'))
    assert [p for p, _ in checks] == [Path(prepared['installer']), target]
    assert all(v == '2.3.0' for _, v in checks)


@pytest.mark.parametrize('failure', ['bad-candidate', 'wrong-version', 'changed-target', 'bad-backup', 'unhealthy'])
def test_invalid_update_never_changes_current_file(prepared, monkeypatch, failure):
    if failure == 'bad-candidate':
        Path(prepared['installer']).write_bytes(b'MZ' + b'bad' * 1024)
    elif failure == 'wrong-version':
        prepared['version'] = '2.1.0'
    elif failure == 'changed-target':
        Path(prepared['executable']).write_bytes(b'MZ' + b'other' * 1024)
    elif failure == 'bad-backup':
        (Path(prepared['backup']) / 'EoingPDF.exe').write_bytes(b'broken')
    monkeypatch.setattr(portable, 'runtime_healthy', lambda *args: False)
    before = Path(prepared['executable']).read_bytes()
    with pytest.raises(ValueError):
        portable.apply(prepared)
    assert Path(prepared['executable']).read_bytes() == before


def test_manual_restore_uses_only_bound_target(prepared):
    prepared.pop('installer')
    target = Path(prepared['executable'])
    target.write_bytes(b'MZ' + b'updated' * 1024)
    prepared['current_digest'] = digest(target)
    assert portable.apply(prepared) == 'restored'
    assert digest(target) == portable.validate(prepared['backup'], target)['sha256']
    with pytest.raises(ValueError):
        portable.validate(prepared['backup'], target.with_name('unrelated.exe'))


def test_rename_sharing_violation_retry_never_leaves_missing_exe(prepared, monkeypatch):
    real_replace = os.replace
    calls = []
    def replace(source, target):
        assert Path(target).is_file()
        assert digest(Path(target)) == prepared['current_digest']
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError('onefile bootloader cleanup')
        real_replace(source, target)
    monkeypatch.setattr(portable.os, 'replace', replace)
    monkeypatch.setattr(portable.time, 'sleep', lambda seconds: None)
    portable.replace_file(prepared['installer'], prepared['executable'], prepared['digest'], prepared['current_digest'])
    assert len(calls) == 2
    assert digest(Path(prepared['executable'])) == prepared['digest']


def test_post_replace_timeout_keeps_backup_and_does_not_restore_over_live_probe(prepared, monkeypatch):
    checks = Mock(side_effect=[True, subprocess.TimeoutExpired('probe', 60)])
    monkeypatch.setattr(portable, 'runtime_healthy', checks)
    with pytest.raises(subprocess.TimeoutExpired):
        portable.apply(prepared)
    assert digest(Path(prepared['executable'])) == prepared['digest']
    assert portable.validate(prepared['backup'], prepared['executable'])['sha256'] == prepared['current_digest']


@pytest.mark.parametrize('metadata', [[], None, {'schema': 1}, {'schema': 2}, 'x' * 8193],
                         ids=['list', 'null', 'incomplete', 'wrong-schema', 'oversize'])
def test_invalid_manifests_are_not_available_for_restore(prepared, monkeypatch, metadata):
    backup = Path(prepared['backup'])
    (backup / 'manifest.json').write_text(json.dumps(metadata), encoding='utf-8')
    monkeypatch.setattr(portable, 'backup_root', lambda: backup.parent)
    assert portable.latest(prepared['executable']) is None


@pytest.mark.skipif(os.name != 'nt', reason='Windows parent process wait')
def test_real_helper_waits_for_owned_parent_and_restores(prepared):
    prepared.pop('installer')
    target = Path(prepared['executable'])
    target.write_bytes(b'MZ' + b'new' * 1024)
    prepared['current_digest'] = digest(target)
    parent = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
                              stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    child = None
    try:
        prepared['pid'] = parent.pid
        child = subprocess.Popen([sys.executable, 'main.py', '--maintenance-child'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW)
        child.stdin.write(json.dumps(prepared).encode())
        child.stdin.close()
        child.stdin = None
        deadline = time.monotonic() + 10
        while (state := read_status(prepared['report'])) is None:
            assert child.poll() is None and time.monotonic() < deadline
            time.sleep(.025)
        assert state['state'] == 'ready'
        Path(prepared['report']).with_suffix('.go').write_text('replace')
        time.sleep(.15)
        assert digest(target) == prepared['current_digest'] and child.poll() is None
        parent.stdin.close()
        parent.wait(timeout=5)
        output = child.communicate(timeout=10)
        assert child.returncode == 0, output
        assert read_status(prepared['report'])['state'] == 'restored'
        assert digest(target) == portable.validate(prepared['backup'], target)['sha256']
    finally:
        for process in (child, parent):
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


def test_source_build_cannot_claim_to_be_portable(tmp_path):
    report = tmp_path / 'health.json'
    result = subprocess.run([sys.executable, 'main.py', '--health-check', str(report), 'nonce', '2.2.0', 'onefile'],
                            capture_output=True, timeout=10)
    assert result.returncode == 1 and not report.exists()
