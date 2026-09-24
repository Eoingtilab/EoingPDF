"""Run real frozen child processes using generated, non-user documents."""
import argparse
import io
import ezdxf
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
import pymupdf as pdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', default='release/EoingPDF/EoingPDF.exe')
    args = parser.parse_args()
    executable = Path(args.exe).resolve()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='frozen-smoke-', dir=root / 'temp') as folder:
        folder = Path(folder)
        health_report = folder / 'health.json'
        import secrets
        nonce = secrets.token_hex(16)
        health = subprocess.run([str(executable), '--health-check', str(health_report), nonce],
                                capture_output=True, timeout=40)
        assert health.returncode == 0, (health.returncode, health.stderr)
        assert json.loads(health_report.read_text(encoding='utf-8')) == {'ok': True, 'nonce': nonce}
        print('PASS: frozen runtime health check, PDF render and bundled font')
        source = folder / 'source.pdf'
        with pdf.open() as document:
            page = document.new_page(width=360, height=160)
            page.insert_text((30, 70), 'HELLO WORLD 123456', fontsize=24)
            page.draw_line((30, 90), (220, 110))
            raster = page.get_pixmap(matrix=pdf.Matrix(2, 2))
            document.save(source)
        scan = folder / 'scan.pdf'
        with pdf.open() as document:
            page = document.new_page(width=360, height=160)
            page.insert_image(page.rect, stream=raster.tobytes('png'))
            document.save(scan)
        original = source.read_bytes()
        for operation, input_path, extension, options in (
            ('svg', source, '.zip', {}),
            ('dxf', source, '.zip', {}),
            ('outlines', source, '.pdf', {}),
            ('markdown', source, '.md', {}),
            ('watermark_text', source, '.pdf', {'watermark_text': 'TEST'}),
            ('deskew', scan, '.pdf', {}),
            ('safe_submission', scan, '.pdf', {}),
            ('print_light', source, '.pdf', {}),
            ('searchable', scan, '.pdf', {}),
            ('booklet', source, '.pdf', {}),
        ):
            target = folder / (operation + extension)
            packet = dict(source=str(input_path), target=str(target), operation=operation,
                          cancel_path=str(folder / 'cancel'), **options)
            result = subprocess.run([str(executable), '--transform-child'], input=json.dumps(packet).encode(),
                                    capture_output=True, timeout=90)
            assert result.returncode == 0, (operation, result.returncode)
            events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith(b'{')]
            assert any(event.get('type') == 'result' and event.get('success') for event in events), (operation, events)
            assert target.is_file() and target.stat().st_size > 0
            if extension == '.zip':
                with zipfile.ZipFile(target) as archive:
                    assert archive.testzip() is None
                    if operation == 'dxf':
                        drawing = ezdxf.read(io.StringIO(archive.read('page-00001.dxf').decode('utf-8')))
                        assert not drawing.audit().has_errors and len(drawing.modelspace()) > 0
                    else:
                        assert archive.namelist() == ['page-00001.svg']
            elif extension == '.md':
                assert 'HELLO WORLD' in target.read_text(encoding='utf-8')
            else:
                with pdf.open(target) as document:
                    assert len(document) > 0
                    if operation == 'outlines':
                        assert not document[0].get_fonts(full=True) and not document[0].get_text().strip()
                    if operation == 'searchable':
                        assert 'HELLO' in document[0].get_text().upper()
                    if operation == 'watermark_text':
                        assert 'TEST' in document[0].get_text()
            print(f'PASS frozen: {operation}', flush=True)
        assert source.read_bytes() == original
        documents = folder / 'search-documents'
        documents.mkdir()
        (documents / 'native.pdf').write_bytes(original)
        (documents / 'scan.pdf').write_bytes(scan.read_bytes())
        database = folder / 'search.sqlite3'
        search_options = dict(model_folder=str(executable.parent / '_internal/assets/search'),
            folder=str(documents), database=str(database), staged=str(folder / 'pending.sqlite3'),
            cancel_path=str(folder / 'search-cancel'), use_ocr=True, query='HELLO WORLD')
        for mode in ('prepare', 'complete', 'search'):
            result = subprocess.run([str(executable), '--search-child'],
                input=json.dumps(dict(search_options, mode=mode)).encode(), capture_output=True, timeout=90)
            assert result.returncode == 0, (mode, result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith(b'{')]
            final = [event for event in events if event.get('type') == 'result']
            assert len(final) == 1 and final[0].get('success'), (mode, events)
            response = json.loads(final[0]['message'])
            if mode == 'prepare':
                assert response['updated'] == 2 and response['error_count'] == 0, response
            if mode == 'search':
                assert {Path(item['path']).name for item in response} == {'native.pdf', 'scan.pdf'}, response
                assert all(item['page'] == 0 and 'HELLO' in item['text'].upper() for item in response)
        assert database.exists() and not Path(search_options['staged']).exists()
        print('PASS frozen: bundled ONNX native/OCR search, staged publication and matching pages', flush=True)


if __name__ == '__main__':
    main()
