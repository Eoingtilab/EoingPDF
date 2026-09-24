"""Exercise the batch wrapper and exit propagation through a recording EXE."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def script(tmp_path):
    folder = tmp_path / '한글 folder & batch'
    folder.mkdir()
    script = folder / 'install-silent.cmd'
    shutil.copyfile(ROOT / 'packaging/install-silent.cmd', script)
    return script


def invoke(script, args, **environment):
    # cmd parses the script exactly as an administrator's deployment batch does.
    command = f'""{script}" {args}"'
    # Supply cmd syntax directly; list2cmdline escaping is for C argv parsers.
    return subprocess.run(f'"{os.environ["COMSPEC"]}" /d /s /c {command}',
                          env=dict(os.environ, **environment), capture_output=True, timeout=20)


def test_silent_script_requires_explicit_mode_and_unambiguous_installer(script):
    assert invoke(script, '').returncode == 64
    assert invoke(script, '/S').returncode == 2
    for version in ('1.0.0', '2.0.0'):
        (script.parent / f'EoingPDF-{version}-Setup-x64.exe').write_bytes(b'not executed')
    assert invoke(script, '/S').returncode == 3


@pytest.mark.parametrize('exit_code', [0, 20, 5])
def test_silent_script_preserves_paths_and_installer_exit_code(script, exit_code):
    source = script.parent / 'Recorder.cs'
    source.write_text('''using System; using System.IO;
class Recorder { static int Main(string[] args) {
File.WriteAllLines(Environment.GetEnvironmentVariable("EOING_SILENT_TEST_REPORT"), args);
return int.Parse(Environment.GetEnvironmentVariable("EOING_SILENT_TEST_EXIT")); }}''')
    executable = script.parent / 'EoingPDF-2.2.0-Setup-x64.exe'
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/out:' + str(executable), str(source)],
                   check=True, capture_output=True, timeout=30)
    report = script.parent / 'arguments.txt'
    target = script.parent / 'destination & space'
    log = script.parent / 'log ! progress.txt'
    result = invoke(script, f'/S /DIR="{target}" /LOG="{log}"',
                    EOING_SILENT_TEST_REPORT=str(report), EOING_SILENT_TEST_EXIT=str(exit_code))
    assert result.returncode == exit_code, result.stderr
    arguments = report.read_text(encoding='utf-8-sig').splitlines()
    for switch in ('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-'):
        assert switch in arguments
    assert '/DIR=' + str(target) in arguments
    assert '/LOG=' + str(log) in arguments
