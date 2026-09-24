"""Exercise the standalone EXE in isolation, without registering user shell keys."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True)
    original = Path(parser.parse_args().exe).resolve()
    with tempfile.TemporaryDirectory(prefix='portable-smoke-', dir=ROOT / 'temp') as name:
        folder = Path(name)
        app_folder = folder / 'single-file'
        app_folder.mkdir()
        executable = app_folder / '이름 변경 portable.exe'
        shutil.copyfile(original, executable)
        assert list(app_folder.iterdir()) == [executable]
        env = dict(os.environ, LOCALAPPDATA=str(folder / 'local'), QT_QPA_PLATFORM='offscreen')
        nonce = secrets.token_hex(16)
        report = folder / 'health.json'
        process = subprocess.run([str(executable), '--health-check', str(report), nonce], env=env,
                                 capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        assert process.returncode == 0, (process.returncode, process.stderr)
        assert json.loads(report.read_text()) == {'ok': True, 'nonce': nonce}
        source = folder / 'original.pdf'
        with pdf.open() as doc:
            doc.new_page().insert_text((70, 80), 'STANDALONE PDF')
            doc.save(source)
        content = source.read_bytes()
        target = folder / 'outlines.pdf'
        packet = dict(source=str(source), target=str(target), operation='outlines', cancel_path=str(folder / 'cancel'))
        process = subprocess.run([str(executable), '--transform-child'], input=json.dumps(packet).encode(),
                                 env=env, capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        assert process.returncode == 0, (process.returncode, process.stderr)
        with pdf.open(target) as doc:
            assert len(doc) == 1 and not doc[0].get_fonts()
        # Use only the existing isolated synthetic-license test helper.
        license_folder = folder / 'local/EoingPDF/license'
        license_folder.mkdir(parents=True)
        seed = subprocess.run([sys.executable, str(ROOT / 'tests/seed_test_license.py'), str(license_folder)],
                              capture_output=True, timeout=20)
        assert seed.returncode == 0
        screenshot = folder / 'viewer.png'
        process = subprocess.run([str(executable), str(source), '--skip-update-once', '--screenshot', str(screenshot)],
                                 env=env, capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        assert process.returncode == 0 and screenshot.is_file(), (process.returncode, process.stderr)
        dock_image = folder / 'dock.png'
        process = subprocess.run([str(executable), '--dock', str(source), '--skip-update-once', '--screenshot', str(dock_image)],
                                 env=env, capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        assert process.returncode == 0 and dock_image.is_file(), (process.returncode, process.stderr)
        documents = folder / 'search-documents'
        documents.mkdir()
        (documents / 'source.pdf').write_bytes(content)
        options = dict(folder=str(documents), database=str(folder / 'search.sqlite3'),
                       staged=str(folder / 'pending.sqlite3'), cancel_path=str(folder / 'search-cancel'),
                       query='STANDALONE PDF')
        for mode in ('prepare', 'complete', 'search'):
            # No external model path: each renamed onefile child must use its own extraction.
            process = subprocess.run([str(executable), '--search-child'], env=env,
                                     input=json.dumps(dict(options, mode=mode)).encode(), capture_output=True,
                                     timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
            assert process.returncode == 0, (mode, process.returncode, process.stderr)
            events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith(b'{')]
            final = [event for event in events if event.get('type') == 'result']
            assert len(final) == 1 and final[0].get('success'), (mode, events)
            if mode == 'search':
                results = json.loads(final[0]['message'])
                assert len(results) == 1 and 'STANDALONE PDF' in results[0]['text']
        assert source.read_bytes() == content
        assert list(app_folder.iterdir()) == [executable]
        results = ROOT / 'temp/portable-validation'
        results.mkdir(exist_ok=True)
        shutil.copyfile(screenshot, results / 'renamed-viewer.png')
        shutil.copyfile(dock_image, results / 'renamed-dock.png')
        (results / 'report.json').write_text(json.dumps({'standalone': True, 'renamed_exe': True,
            'health': True, 'transform': True, 'viewer': True, 'dock': True, 'bundled_search': True,
            'source_preserved': True,
            'shell_registered': False, 'auto_update': 'portable package integration pending'}), encoding='utf-8')
    print('PASS: single renamed EXE, embedded font/PDF/ONNX engine, isolated transform, offline viewer/dock and source preservation')


if __name__ == '__main__':
    main()
