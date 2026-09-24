"""Frozen onefile update/rollback in an isolated folder; no server or shell changes.

The old-version manifest is synthetic; both EXEs contain this build. This checks
the real bootloader/file-lock/restart path, not a live cross-version EDD release.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.portable_update import create, runtime_healthy
from eoingpdf.update_helper import read_status
from eoingpdf.update_snapshot import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True)
    args = parser.parse_args()
    distribution = Path(args.exe).resolve()
    version = (ROOT / 'VERSION').read_text(encoding='utf-8-sig').strip()
    with tempfile.TemporaryDirectory(prefix='portable-update-', dir=ROOT / 'temp') as temporary:
        folder = Path(temporary)
        target = folder / 'app' / '이름 바꾼 portable.exe'
        target.parent.mkdir()
        shutil.copyfile(distribution, target)
        neighbor = target.parent / '사용자 문서.pdf'
        neighbor.write_bytes(b'USER DOCUMENT MUST REMAIN')
        backup = create(target, folder / 'backups', '0.0.1')
        original = digest(target)
        assert runtime_healthy(target, version)
        assert not runtime_healthy(target, '9999.0.0'), 'Wrong embedded version accepted'
        states = []
        for operation in ('update', 'restore'):
            report = folder / f'{operation}.json'
            parent = subprocess.Popen([str(target), '--transform-child'], stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
            child = None
            try:
                packet = dict(kind='onefile', backup=str(backup), executable=str(target),
                    current_digest=digest(target), pid=parent.pid, report=str(report), restart=False)
                if operation == 'update':
                    packet.update(installer=str(distribution), digest=digest(distribution), version=version)
                child = subprocess.Popen([str(backup / 'EoingPDF.exe'), '--maintenance-child'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
                child.stdin.write(json.dumps(packet).encode())
                child.stdin.close()
                child.stdin = None
                deadline = time.monotonic() + 60
                while (state := read_status(report)) is None:
                    assert child.poll() is None and time.monotonic() < deadline, 'Helper not ready'
                    time.sleep(.05)
                assert state['state'] == 'ready', state
                report.with_suffix('.go').write_text('replace')
                time.sleep(.2)
                assert parent.poll() is None and child.poll() is None
                assert read_status(report)['state'] == 'ready'
                parent.stdin.close()
                parent.wait(timeout=30)
                output = child.communicate(timeout=150)
                assert child.returncode == 0, (output, read_status(report))
                states.append(read_status(report)['state'])
                assert states[-1] == ('updated' if operation == 'update' else 'restored')
                assert digest(target) == original
                assert neighbor.read_bytes() == b'USER DOCUMENT MUST REMAIN'
                assert sorted(p.name for p in target.parent.iterdir()) == sorted([target.name, neighbor.name])
                print(f'PASS frozen portable {operation}: waits for loaded EXE, retains filename and user file', flush=True)
            finally:
                for process in (child, parent):
                    if process is not None and process.poll() is None:
                        process.terminate()
                        process.wait(timeout=15)
        assert runtime_healthy(target, version)
        output = ROOT / 'temp/portable-validation/update-report.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(dict(states=states, renamed_exe=True, preserved_user_file=True,
            embedded_version_checked=True, live_cross_version=False, manifest_version_fixture='0.0.1'), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
