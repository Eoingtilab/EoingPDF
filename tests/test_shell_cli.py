"""Launch the real entry point with fake shell operations, never real registry writes."""
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = r'''
import ctypes, runpy, sys, types
from pathlib import Path
root, action, failure, report, stream = sys.argv[1:]
sys.path.insert(0, str(Path(root) / 'src'))
def forbidden_popup(*args):
    raise SystemExit(91)
ctypes.windll.user32.MessageBoxW = forbidden_popup
shell = types.ModuleType('eoingpdf.shell')
def operation():
    if failure == 'permission': raise PermissionError('test denied')
    if failure == 'missing': raise ValueError('test missing binary')
    if failure == 'os': raise OSError('test IO error')
shell.install = shell.uninstall = operation
shell.open_default_settings = lambda: Path(report + '.settings').write_text('opened')
sys.modules['eoingpdf.shell'] = shell
sys.argv = [str(Path(root) / 'main.py'), action, '--shell-result', report]
if stream == 'none': sys.stderr = None
runpy.run_path(sys.argv[0], run_name='__main__')
'''


@pytest.mark.parametrize('action', ['--install-menu', '--register-shell', '--uninstall-menu'])
@pytest.mark.parametrize('failure,code', [('permission', 2), ('missing', 1), ('os', 1), ('none', 0)])
@pytest.mark.parametrize('stream', ['normal', 'none'])
def test_shell_process_exits_without_dialog(tmp_path, action, failure, code, stream):
    report = tmp_path / 'result.json'
    result = subprocess.run([sys.executable, '-c', BOOTSTRAP, str(ROOT), action,
                             failure, str(report), stream], capture_output=True, timeout=10)
    assert result.returncode == code, result.stderr
    data = json.loads(report.read_text(encoding='utf-8-sig'))
    assert data['exit_code'] == code
    assert data['action'] == action
    assert Path(str(report) + '.settings').exists() == (code == 0 and action == '--install-menu')


def test_unwritable_report_does_not_hide_registration_error(tmp_path):
    report = tmp_path / 'directory'
    report.mkdir()
    result = subprocess.run([sys.executable, '-c', BOOTSTRAP, str(ROOT), '--register-shell',
                             'permission', str(report), 'none'], capture_output=True, timeout=10)
    assert result.returncode == 2
