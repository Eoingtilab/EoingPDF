"""Validate automatic table forms and Korean entry in the distributable EXE."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import pymupdf as pdf
from pypdf import PdfReader
from pypdf.generic import NameObject

ROOT = Path(__file__).resolve().parents[1]


def make_source(path):
    with pdf.open() as document:
        for rotation in (0, 90, 180, 270):
            page = document.new_page(width=500, height=400)
            for x in (40, 160, 440):
                for y in (40, 80, 120):
                    page.draw_rect(pdf.Rect(x - .25, y, x + .25, y + 40), color=None, fill=(0, 0, 0))
            for y in (40, 80, 120, 160):
                for x0, x1 in ((40, 160), (160, 440)):
                    page.draw_rect(pdf.Rect(x0, y - .25, x1, y + .25), color=None, fill=(0, 0, 0))
            for y, label in zip((65, 105, 145), ('Name', 'Address', 'Notes')):
                page.insert_text((60, y), label)
            page.draw_rect(pdf.Rect(40, 200, 60, 220))
            page.set_rotation(rotation)
        document.save(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--source', type=Path, help='Optional generated Office PDF to test as well')
    args = parser.parse_args()
    executable = args.exe.resolve()
    with tempfile.TemporaryDirectory(prefix='frozen-forms-', dir=ROOT / 'temp') as name:
        folder = Path(name)
        synthetic = folder / 'table.pdf'
        make_source(synthetic)
        sources = [(synthetic, 16)]
        if args.source:
            sources.append((args.source.resolve(), 3))
        for index, (source, expected_count) in enumerate(sources):
            original = source.read_bytes()

            def run(operation, target, **values):
                packet = dict(source=str(source), target=str(target), operation=operation,
                              cancel_path=str(folder / 'cancel'), locale='ko-KR', **values)
                result = subprocess.run([str(executable), '--transform-child'],
                    input=json.dumps(packet).encode(), capture_output=True, timeout=90,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                assert result.returncode == 0, (result.returncode, result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                assert events and events[-1].get('type') == 'result' and events[-1].get('success'), events

            form = folder / f'form-{index}.pdf'
            run('auto_forms', form)
            values, expected = {}, {}
            with pdf.open(form) as document:
                total = 0
                for page in document:
                    for field in page.widgets() or ():
                        total += 1
                        checked = field.field_type == pdf.PDF_WIDGET_TYPE_CHECKBOX
                        values[str(field.xref)] = True if checked else '홍길동 서울시'
                        expected[field.field_name] = field.on_state() if checked else '홍길동 서울시'
                assert total == expected_count, (total, expected_count)
            filled = folder / f'filled-{index}.pdf'
            # The filled source is the new interactive copy, preserving the original.
            source_form = source
            source = form
            run('fill_forms', filled, form_values=values)
            source = source_form
            with pdf.open(filled) as document:
                found = {}
                for page in document:
                    assert '홍길동 서울시' in page.get_text()
                    for field in page.widgets() or ():
                        found[field.field_name] = field.field_value
                        assert document.xref_get_key(field.xref, 'AP/N')[0] in ('xref', 'dict')
                    assert page.get_pixmap().width > 0
                assert found == expected
            canonical = PdfReader(filled).get_fields()
            # Checkbox states are PDF names (/Yes), while text values are strings.
            canonical_values = {key: (str(value['/V']).removeprefix('/')
                                      if isinstance(value['/V'], NameObject) else value['/V'])
                                for key, value in canonical.items()}
            assert canonical_values == expected, (canonical_values, expected)
            assert source.read_bytes() == original
            print(f'PASS frozen forms: {expected_count} fields, shared/filled borders, Korean values and source preserved', flush=True)


if __name__ == '__main__':
    main()
