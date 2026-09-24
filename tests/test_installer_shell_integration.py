"""Run Inno's real postinstall hook in an isolated, unregistered test installer."""
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def shell_test_setup(tmp_path_factory):
    compiler = ROOT / 'build/tools/InnoSetup/ISCC.exe'
    csc = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file() or not csc.is_file():
        pytest.skip('Requires the local Inno Setup and .NET Framework compilers')
    folder = tmp_path_factory.mktemp('shell-installer')
    source = folder / 'ShellStub.cs'
    stub = folder / 'EoingPDF.exe'
    source.write_text('''
using System;
using System.IO;
class ShellStub {
    static int Main(string[] args) {
        if (args.Length != 3 || args[0] != "--register-shell" || args[1] != "--shell-result") return 99;
        int code = int.Parse(Environment.GetEnvironmentVariable("EOING_TEST_SHELL_EXIT"));
        File.WriteAllText(args[2], "test shell result: " + code);
        return code;
    }
}
''', encoding='utf-8')
    built = subprocess.run([str(csc), '/nologo', '/target:winexe', '/out:' + str(stub), str(source)],
                           capture_output=True, timeout=30)
    assert built.returncode == 0, built.stdout + built.stderr
    script = folder / 'TestSetup.iss'
    include = ROOT / 'packaging/shell_registration.iss'
    script.write_text(fr'''
[Setup]
AppName=EoingPDF shell hook test
AppVersion=1.0
DefaultDirName={{tmp}}\EoingPDFShellTest
PrivilegesRequired=lowest
Uninstallable=no
DisableProgramGroupPage=yes
OutputDir={folder}
OutputBaseFilename=ShellHookTest
Compression=none
CloseApplications=no
[Files]
Source: "{stub}"; DestDir: "{{app}}"
[Code]
#include "{include}"
''', encoding='utf-8-sig')
    built = subprocess.run([str(compiler), '/Q', str(script)], capture_output=True, timeout=30)
    assert built.returncode == 0, built.stdout + built.stderr
    return folder / 'ShellHookTest.exe'


@pytest.mark.parametrize('shell_code,setup_code', [(0, 0), (1, 20), (2, 20)])
def test_silent_installer_propagates_shell_failure(shell_test_setup, tmp_path, shell_code, setup_code):
    app = tmp_path / 'app'
    log = tmp_path / 'setup.log'
    environment = dict(os.environ, EOING_TEST_SHELL_EXIT=str(shell_code))
    result = subprocess.run([str(shell_test_setup), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                             '/NORESTART', '/DIR=' + str(app), '/LOG=' + str(log)],
                            env=environment, capture_output=True, timeout=30)
    assert result.returncode == setup_code, result.stderr
    assert (app / 'EoingPDF.exe').is_file()
    text = log.read_text(encoding='utf-8-sig')
    assert f'EoingPDF shell registration exit code: {shell_code}' in text
    assert f'test shell result: {shell_code}' in text
    assert ('installation is incomplete' in text) == (shell_code != 0)
