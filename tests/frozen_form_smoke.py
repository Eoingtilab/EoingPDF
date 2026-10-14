"""Validate automatic table forms and Korean entry in the distributable EXE."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import pymupdf as pdf
from pypdf import PdfReader
from pypdf.generic import NameObject

ROOT = Path(__file__).resolve().parents[1]


class ChildRunner:
    def __init__(self, command, folder):
        self.command = command
        self.folder = folder

    def transform(self, source, target, operation, minimum_request_bytes=0, **values):
        packet = dict(source=str(source), target=str(target), operation=operation,
                      cancel_path=str(self.folder / 'cancel'), locale='ko-KR', **values)
        payload = json.dumps(packet, ensure_ascii=True).encode('utf-8')
        assert len(payload) > minimum_request_bytes, (len(payload), minimum_request_bytes)
        result = subprocess.run([*self.command, '--transform-child'], input=payload,
            capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, (result.returncode, result.stderr)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        assert events and events[-1].get('type') == 'result' and events[-1].get('success'), events
        return len(payload)


def source_hash(path):
    return hashlib.sha256(path.read_bytes()).digest()


def make_shared_source(path):
    """A single canonical text field appears twice on each of three pages."""
    with pdf.open() as document:
        children = []
        for number in range(3):
            page = document.new_page(width=650, height=850)
            page.insert_text((65, 110), f'SHARED PAGE {number + 1}')
            for top in (160, 240):
                field = pdf.Widget()
                field.field_name = 'shared'
                field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
                field.field_value = 'Original'
                field.rect = pdf.Rect(65, top, 365, top + 35)
                children.append(page.add_widget(field).xref)
            page.set_cropbox(pdf.Rect(30, 50, 630, 850))
            page.set_rotation((number + 1) * 90)
        parent = document.get_new_xref()
        document.update_object(parent, '<</FT /Tx /T (shared) /V (Original) /Kids [' +
                               ' '.join(f'{xref} 0 R' for xref in children) + ']>>')
        for xref in children:
            original = document.xref_object(xref)
            document.update_object(xref, original.replace('/FT /Tx', '').replace('/T (shared)', '')
                                   .replace('/V (Original)', ''))
            document.xref_set_key(xref, 'Parent', f'{parent} 0 R')
        document.xref_set_key(document.pdf_catalog(), 'AcroForm/Fields', f'[{parent} 0 R]')
        document.save(path)


def validate_shared(path, page_numbers, value):
    reader = PdfReader(path)
    fields = reader.get_fields() or {}
    assert set(fields) == {'shared'}, fields.keys()
    assert fields['shared']['/V'] == value
    widgets = [reference for page in reader.pages for reference in page.get('/Annots', ())
               if reference.get_object().get('/Subtype') == '/Widget']
    assert len(widgets) == len(page_numbers) * 2
    for reference in widgets:
        widget = reference.get_object()
        parent = widget['/Parent'].get_object()
        assert parent['/T'] == 'shared' and parent['/V'] == value
        assert set(parent['/Kids']) == set(widgets)
        assert len(widget['/AP']['/N'].get_object().get_data()) > 0
    with pdf.open(path) as document:
        assert document.page_count == len(page_numbers)
        for page, number in zip(document, page_numbers):
            assert f'SHARED PAGE {number}' in page.get_text()
            assert page.get_text().count(value) == 2, (number, page.get_text())
            assert page.rotation == number * 90
            assert page.cropbox == pdf.Rect(30, 50, 630, 850)
            assert page.get_pixmap().width > 0


def test_shared_forms(runner, folder):
    source = folder / 'shared-source.pdf'
    make_shared_source(source)
    original_hash = source_hash(source)
    reverse = folder / 'shared-reverse.pdf'
    runner.transform(source, reverse, 'reverse')
    validate_shared(reverse, [3, 2, 1], 'Original')
    archive_path = folder / 'shared-selection.zip'
    runner.transform(source, archive_path, 'split_ranges', split_ranges='3-2,1')
    copies = [(reverse, [3, 2, 1])]
    with zipfile.ZipFile(archive_path) as archive:
        assert len(archive.namelist()) == 2
        for index, numbers in enumerate(([3, 2], [1])):
            copied = folder / f'shared-selected-{index}.pdf'
            copied.write_bytes(archive.read(archive.namelist()[index]))
            validate_shared(copied, numbers, 'Original')
            copies.append((copied, numbers))
    for index, (copied, numbers) in enumerate(copies):
        copied_hash = source_hash(copied)
        with pdf.open(copied) as document:
            key = str(next(document[0].widgets()).xref)
        filled = folder / f'shared-filled-{index}.pdf'
        runner.transform(copied, filled, 'fill_forms', form_values={key: '공유 필드 검토 완료'})
        validate_shared(filled, numbers, '공유 필드 검토 완료')
        assert source_hash(copied) == copied_hash
    assert source_hash(source) == original_hash
    print('PASS frozen shared forms: reverse, selected split copies, canonical Parent/Kids, Korean V/AP and source hashes', flush=True)


def test_large_korean_request(runner, folder):
    source, target = folder / 'large-entry-source.pdf', folder / 'large-entry-filled.pdf'
    with pdf.open() as document:
        for number in range(5):
            page = document.new_page(width=595, height=842)
            page.insert_text((35, 40), f'KOREAN ENTRY PAGE {number + 1}')
            for row in range(10):
                field = pdf.Widget()
                field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
                field.field_name = f'entry_{number}_{row}'
                field.field_flags = pdf.PDF_TX_FIELD_IS_MULTILINE
                field.rect = pdf.Rect(35, 60 + row * 70, 560, 125 + row * 70)
                page.add_widget(field)
        document.save(source)
    original_hash = source_hash(source)
    values, expected = {}, {}
    with pdf.open(source) as document:
        for page in document:
            for field in page.widgets() or ():
                value = field.field_name + '\n' + '한글 양식 입력 확인 내용입니다. ' * 24
                values[str(field.xref)] = value
                expected[field.field_name] = value
    size = runner.transform(source, target, 'fill_forms', minimum_request_bytes=65536, form_values=values)
    canonical = PdfReader(target).get_fields() or {}
    assert {key: field['/V'] for key, field in canonical.items()} == expected
    with pdf.open(target) as document:
        for page in document:
            for field in page.widgets() or ():
                assert field.field_value == expected[field.field_name]
                assert document.xref_get_key(field.xref, 'AP/N')[0] == 'xref'
            assert '한글 양식 입력 확인 내용입니다.' in page.get_text()
            assert page.get_pixmap().width > 0
    assert source_hash(source) == original_hash
    print(f'PASS frozen Korean entry: {size} request bytes, 50 fields, canonical values, appearances and source hash', flush=True)


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
    runtime = parser.add_mutually_exclusive_group(required=True)
    runtime.add_argument('--exe', type=Path)
    runtime.add_argument('--source-mode', action='store_true', help='Run the same child protocol against main.py before packaging')
    parser.add_argument('--source', type=Path, help='Optional generated Office PDF to test as well')
    args = parser.parse_args()
    command = [str(args.exe.resolve())] if args.exe else [sys.executable, str(ROOT / 'main.py')]
    with tempfile.TemporaryDirectory(prefix='frozen-forms-', dir=ROOT / 'temp') as name:
        folder = Path(name)
        runner = ChildRunner(command, folder)
        synthetic = folder / 'table.pdf'
        make_source(synthetic)
        sources = [(synthetic, 16)]
        if args.source:
            sources.append((args.source.resolve(), 3))
        for index, (source, expected_count) in enumerate(sources):
            original = source.read_bytes()

            form = folder / f'form-{index}.pdf'
            runner.transform(source, form, 'auto_forms')
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
            runner.transform(form, filled, 'fill_forms', form_values=values)
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
        test_shared_forms(runner, folder)
        test_large_korean_request(runner, folder)


if __name__ == '__main__':
    main()
