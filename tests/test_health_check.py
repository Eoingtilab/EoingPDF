import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf import update_helper as helper


def test_real_source_runtime_probe(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    root = Path(__file__).resolve().parents[1]
    def start(command, **kwargs):
        assert command[1] == '--health-check'
        return real_popen([sys.executable, str(root / 'main.py'), *command[1:]], **kwargs)
    monkeypatch.setattr(helper.subprocess, 'Popen', start)
    assert helper.runtime_healthy(tmp_path)


@pytest.mark.parametrize('result', ['missing', 'wrong-nonce', 'invalid-json', 'oversize', 'exit-error'])
def test_probe_rejects_incomplete_or_invalid_success(tmp_path, monkeypatch, result):
    process = Mock()
    process.wait.return_value = 1 if result == 'exit-error' else 0
    def start(command, **kwargs):
        report = Path(command[2])
        if result != 'missing':
            report.write_text({'wrong-nonce': json.dumps({'ok': True, 'nonce': 'wrong'}),
                'invalid-json': '{', 'oversize': 'x' * 5000,
                'exit-error': json.dumps({'ok': True, 'nonce': command[3]})}[result])
        return process
    monkeypatch.setattr(helper.subprocess, 'Popen', start)
    assert not helper.runtime_healthy(tmp_path)
    process.kill.assert_not_called()


def test_timed_out_probe_must_exit_before_restore_is_allowed(tmp_path, monkeypatch):
    process = Mock()
    process.wait.side_effect = [subprocess.TimeoutExpired('probe', 30), 1]
    monkeypatch.setattr(helper.subprocess, 'Popen', lambda *args, **kwargs: process)
    assert not helper.runtime_healthy(tmp_path)
    process.kill.assert_called_once()
    process.wait.side_effect = [subprocess.TimeoutExpired('probe', 30), subprocess.TimeoutExpired('probe', 5)]
    with pytest.raises(subprocess.TimeoutExpired):
        helper.runtime_healthy(tmp_path)
