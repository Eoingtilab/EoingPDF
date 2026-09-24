"""Exercise restore from a copied frozen app; never install or change shell state."""
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
from eoingpdf.update_snapshot import create, digest
from eoingpdf.update_helper import read_status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', default=str(ROOT / 'release/EoingPDF'))
    distribution = Path(parser.parse_args().folder).resolve()
    with tempfile.TemporaryDirectory(prefix='frozen-update-', dir=ROOT / 'temp') as temporary:
        folder = Path(temporary)
        install = folder / 'app'
        shutil.copytree(distribution, install)
        version = (install / 'VERSION').read_text(encoding='utf-8-sig').strip()
        extension = install / 'EoingPDF.Explorer.dll'
        assert extension.is_file(), 'Packaged modern shell DLL missing'
        extension_digest = digest(extension)
        backup = create(install, folder / 'backups', version)
        executable = install / 'EoingPDF.exe'
        report = folder / 'status.json'
        # Keep the real frozen runtime loaded until the helper reports ready.
        parent = subprocess.Popen([str(executable), '--transform-child'], stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        child = None
        try:
            (install / 'VERSION').write_text('0.0.0', encoding='utf-8')
            extension.write_bytes(b'MZ-synthetic-replacement-extension')
            child = subprocess.Popen([str(backup / 'EoingPDF.exe'), '--maintenance-child'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            packet = dict(backup=str(backup), install=str(install), report=str(report), pid=parent.pid, restart=False)
            child.stdin.write(json.dumps(packet).encode())
            child.stdin.close(); child.stdin = None
            deadline = time.monotonic() + 60
            while (state := read_status(report)) is None:
                if child.poll() is not None or time.monotonic() > deadline:
                    raise AssertionError('Frozen helper did not become ready')
                time.sleep(.05)
            assert state['state'] == 'ready'
            report.with_suffix('.go').write_text('restore', encoding='ascii')
            time.sleep(.2)
            assert parent.poll() is None
            assert (install / 'VERSION').read_text() == '0.0.0'
            parent.stdin.close(); parent.stdin = None
            parent.wait(timeout=20)
            stdout, stderr = child.communicate(timeout=90)
            assert child.returncode == 0, (stdout, stderr, report.read_text(encoding='utf-8'))
            assert json.loads(report.read_text(encoding='utf-8'))['state'] == 'restored'
            assert (install / 'VERSION').read_text(encoding='utf-8-sig').strip() == version
            assert digest(extension) == extension_digest
            # The restored runtime must actually process a document again.
            import pymupdf as pdf
            source, target = folder / 'source.pdf', folder / 'restored.pdf'
            with pdf.open() as document:
                document.new_page().insert_text((30, 40), 'RESTORED RUNTIME')
                document.save(source)
            packet = dict(source=str(source), target=str(target), operation='outlines', cancel_path=str(folder / 'cancel'))
            result = subprocess.run([str(executable), '--transform-child'], input=json.dumps(packet).encode(),
                                    capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0, (result.stdout, result.stderr)
            with pdf.open(target) as document:
                assert not document[0].get_fonts(full=True)
            print('PASS frozen update: separate backup runtime waits for loaded app exit, restores files and runs again')
        finally:
            for process in (child, parent):
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == '__main__':
    main()
