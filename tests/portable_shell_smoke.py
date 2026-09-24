"""Register a renamed standalone EXE with preservation of workspace registration.

Uses real HKCU registration and always unregisters its own test copy. Never
overwrites another install; the known workspace copy is snapshotted and restored.
LOCALAPPDATA helpers stay in the test directory.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import winreg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf import shell
from eoingpdf.convert import SUPPORTED


def absent(path, value=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            if value is not None:
                winreg.QueryValueEx(key, value)
        return False
    except FileNotFoundError:
        return True


def preflight():
    paths = [r'Software\Classes\Applications\EoingPDF.exe',
             r'Software\Classes\EoingPDF.Document', r'Software\EoingPDF\Capabilities']
    paths += [shell.BASE + '\\EoingPDF2.' + action for action in shell.IDS]
    paths += ['Software\\Classes\\CLSID\\' + clsid for clsid in shell.IDS.values()]
    legacy = [rf'Software\Classes\SystemFileAssociations\{ext}\shell\{name}'
              for ext in SUPPORTED | {'.odt', '.ods', '.odp', '.xps', '.oxps'}
              for name in shell.LEGACY_NAMES]
    for path in legacy:
        if not absent(path):
            raise RuntimeError('Existing registration preserved; smoke test refused: ' + path)
    workspace_owned = shell.registration_status(ROOT / 'release/EoingPDF')['ready']
    snapshots = {}
    for path in paths:
        if not absent(path):
            if not workspace_owned:
                raise RuntimeError('Another installation owns the shell keys; test refused')
            snapshots[path] = shell.snapshot_key(path)
    values = {}
    for path, value in [(r'Software\RegisteredApplications', 'EoingPDF'),
                        (r'Software\Classes\.pdf\OpenWithProgids', 'EoingPDF.Document')]:
        if not absent(path, value):
            if not workspace_owned:
                raise RuntimeError('Existing application association preserved; smoke test refused')
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                values[path, value] = winreg.QueryValueEx(key, value)
    return paths, snapshots, values


def restore_tree(path, data):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        for name, value, kind in data['values']:
            winreg.SetValueEx(key, name, 0, kind, value)
    for name, child in data['children'].items():
        restore_tree(path + '\\' + name, child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True)
    original = Path(parser.parse_args().exe).resolve()
    paths, snapshots, values = preflight()
    with tempfile.TemporaryDirectory(prefix='portable-shell-', dir=ROOT / 'temp') as name:
        folder = Path(name)
        executable = folder / '이름 변경 shell.exe'
        shutil.copyfile(original, executable)
        env = dict(os.environ, LOCALAPPDATA=str(folder / 'local'))

        def invoke(action):
            report = folder / ('report-' + action + '.json')
            result = subprocess.run([str(executable), action, '--shell-result', str(report)],
                                    env=env, capture_output=True, timeout=90,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0, (result.returncode, result.stderr)
            assert json.loads(report.read_text(encoding='utf-8-sig'))['exit_code'] == 0

        try:
            invoke('--register-shell')
            for action, clsid in shell.IDS.items():
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    'Software\\Classes\\CLSID\\' + clsid + r'\LocalServer32') as key:
                    command = winreg.QueryValueEx(key, '')[0]
                    bridge = Path(winreg.QueryValueEx(key, 'ServerExecutable')[0])
                assert command == f'"{bridge}" {action} --app "{executable}"'
                assert bridge.is_file() and bridge.is_relative_to(folder / 'local')
                assert '_MEI' not in command
                assert (bridge.parent / 'pdf_icon.ico').is_file()
            # A second process/extraction must reuse the persisted helper paths.
            first_bridge = bridge
            invoke('--register-shell')
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                'Software\\Classes\\CLSID\\' + shell.IDS['summary'] + r'\LocalServer32') as key:
                assert Path(winreg.QueryValueEx(key, 'ServerExecutable')[0]) == first_bridge
        finally:
            try:
                invoke('--uninstall-menu')
            finally:
                for path, data in snapshots.items():
                    restore_tree(path, data)
                for (path, value), (data, kind) in values.items():
                    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
                        winreg.SetValueEx(key, value, 0, kind, data)
                shell.ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        for path in paths:
            assert shell.snapshot_key(path) == snapshots[path] if path in snapshots else absent(path)
        for (path, value), expected in values.items():
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                assert winreg.QueryValueEx(key, value) == expected
        assert not first_bridge.exists()
        assert executable.is_file()
        output = ROOT / 'temp/portable-validation/shell-report.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps({'renamed_exe': True, 'persistent_helpers': True,
                                      'repeat_registration': True, 'unregistration': True,
                                      'original_registration_preserved': True}), encoding='utf-8')
    print('PASS: renamed standalone EXE, persistent COM helper, repeated registration and clean unregistration')


if __name__ == '__main__':
    main()
