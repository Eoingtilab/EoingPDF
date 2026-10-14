"""Office-style tables and canonical shared-field regression coverage."""
import io
import re
import sys
import zipfile
from pathlib import Path

import pymupdf as pdf
import pytest
from pypdf import PdfReader
from pypdf.generic import NullObject
from PySide6.QtWidgets import QApplication, QLineEdit, QListWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Request, run
from eoingpdf.form_ui import FormDialog
from eoingpdf.forms import candidates, choice_options, choice_selection


def shared_fixture(path, encrypted=False):
    """One logical field with two visible positions on each of three pages."""
    with pdf.open() as document:
        shared_refs = []
        for index in range(3):
            page = document.new_page(width=650, height=850)
            page.insert_text((65, 110), f'PAGE {index + 1}')
            for top in (160, 240):
                field = pdf.Widget()
                field.field_name = 'shared'
                field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
                field.field_value = 'Original'
                field.rect = pdf.Rect(65, top, 365, top + 35)
                shared_refs.append(page.add_widget(field).xref)
            page.set_cropbox(pdf.Rect(30, 50, 630, 850))
            page.set_rotation((index + 1) * 90)
        parent = document.get_new_xref()
        document.update_object(parent, '<</FT /Tx /T (shared) /V (Original) /Kids [' +
                               ' '.join(f'{xref} 0 R' for xref in shared_refs) + ']>>')
        for xref in shared_refs:
            # Remove inherited keys rather than writing PDF null-valued names.
            obj = document.xref_object(xref).replace('/FT /Tx', '').replace('/T (shared)', '').replace('/V (Original)', '')
            document.update_object(xref, obj)
            document.xref_set_key(xref, 'Parent', f'{parent} 0 R')
        document.xref_set_key(document.pdf_catalog(), 'AcroForm/Fields', f'[{parent} 0 R]')
        options = dict(encryption=pdf.PDF_ENCRYPT_AES_256, user_pw='secret', owner_pw='owner') if encrypted else {}
        document.save(path, **options)


def canonical(source, password=''):
    with pdf.open(source) if not isinstance(source, bytes) else pdf.open(stream=source, filetype='pdf') as document:
        if document.needs_pass:
            assert document.authenticate(password)
        reader = PdfReader(io.BytesIO(document.tobytes(encryption=pdf.PDF_ENCRYPT_NONE)))
    fields = reader.get_fields() or {}
    widgets = [entry.get_object() for page in reader.pages for entry in page.get('/Annots', ())
               if entry.get_object().get('/Subtype') == '/Widget']
    for widget in widgets:
        assert len(widget['/AP']['/N'].get_object().get_data()) > 0
        parent = widget['/Parent'].get_object()
        assert parent['/T'] == 'shared'
        assert widget.indirect_reference in parent['/Kids']
        assert set(parent['/Kids']) == {widget.indirect_reference for widget in widgets}
    return fields, widgets


@pytest.mark.parametrize('operation,options', [
    ('reverse', {}), ('watermark_text', {'watermark_text': 'COPY'}),
    ('trim', {}), ('metadata', {}), ('repair', {}),
    ('bates', {'bates_cover': True}),
    ('encrypt', {'user_password': 'new-secret', 'owner_password': 'new-owner'}),
])
@pytest.mark.parametrize('encrypted', (False, True))
def test_common_effects_preserve_shared_canonical_fields(tmp_path, operation, options, encrypted):
    source, target = tmp_path / 'source.pdf', tmp_path / 'effect.pdf'
    shared_fixture(source, encrypted)
    original = source.read_bytes()
    transform(source, target, operation, password='secret' if encrypted else '', **options)
    fields, widgets = canonical(target, 'new-secret' if operation == 'encrypt' else '')
    assert set(fields) == {'shared'}
    assert fields['shared']['/V'] == 'Original'
    assert len(widgets) == 6
    with pdf.open(target) as document:
        if document.needs_pass:
            assert document.authenticate('new-secret')
        expected = [3, 2, 1] if operation == 'reverse' else [1, 2, 3]
        pages = list(document)[1:] if operation == 'bates' else list(document)
        assert len(pages) == 3
        assert [next(int(line.removeprefix('PAGE ')) for line in page.get_text().splitlines() if line.startswith('PAGE '))
                for page in pages] == expected
        assert all(page.get_pixmap().width > 0 for page in pages)
    assert source.read_bytes() == original


@pytest.mark.parametrize('operation', ('split_ranges', 'extract'))
@pytest.mark.parametrize('selection', ('3-1', '2'))
def test_copying_pages_preserves_one_shared_field(tmp_path, operation, selection):
    source = tmp_path / 'source.pdf'
    shared_fixture(source)
    original = source.read_bytes()
    if operation == 'split_ranges':
        target = tmp_path / 'split.zip'
        transform(source, target, operation, split_ranges=selection)
        with zipfile.ZipFile(target) as archive:
            contents = archive.read(archive.namelist()[0])
    else:
        target = run(Request('extract', (str(source),), str(tmp_path / 'output'), selection))
        contents = target.read_bytes()
    fields, widgets = canonical(contents)
    assert set(fields) == {'shared'}
    assert len(widgets) == (6 if selection == '3-1' else 2)
    with pdf.open(stream=contents, filetype='pdf') as document:
        field = next(document[0].widgets())
        key = str(field.xref)
    copied = tmp_path / 'copied.pdf'
    copied.write_bytes(contents)
    filled = tmp_path / 'filled.pdf'
    transform(copied, filled, 'fill_forms', form_values={key: '홍길동'})
    fields, widgets = canonical(filled)
    assert fields['shared']['/V'] == '홍길동'
    assert all(widget['/Parent'].get_object()['/V'] == '홍길동' for widget in widgets)
    with pdf.open(filled) as document:
        assert all(page.get_text().count('홍길동') == 2 for page in document)
    assert source.read_bytes() == original


def test_shared_field_has_one_entry_per_page_and_updates_all_appearances(tmp_path):
    app = QApplication.instance() or QApplication([])
    source, target = tmp_path / 'source.pdf', tmp_path / 'filled.pdf'
    shared_fixture(source)
    dialog = FormDialog(source, 0)
    try:
        assert len(dialog.fields) == 1
        editor = next(iter(dialog.fields.values()))
        assert isinstance(editor, QLineEdit)
        editor.setText('홍길동')
        transform(source, target, 'fill_forms', form_values=dialog.input_values())
        fields, widgets = canonical(target)
        assert fields['shared']['/V'] == '홍길동'
        with pdf.open(target) as document:
            assert all(page.get_text().count('홍길동') == 2 for page in document)
            document[0].get_pixmap(matrix=pdf.Matrix(1.5, 1.5)).save(tmp_path / 'filled-shared.png')
    finally:
        dialog.close()
        app.processEvents()


def test_conflicting_values_for_one_logical_field_are_rejected(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'conflict.pdf'
    shared_fixture(source)
    with pdf.open(source) as document:
        fields = list(document[0].widgets())
        values = {str(fields[0].xref): 'First', str(fields[1].xref): 'Second'}
    original = source.read_bytes()
    with pytest.raises(ValueError):
        transform(source, target, 'fill_forms', form_values=values)
    assert not target.exists()
    assert source.read_bytes() == original


def shared_choice_fixture(path):
    with pdf.open() as document:
        refs = []
        for _ in range(2):
            page = document.new_page()
            field = pdf.Widget()
            field.field_name = 'shared'
            field.field_type = pdf.PDF_WIDGET_TYPE_LISTBOX
            field.field_flags = pdf.PDF_CH_FIELD_IS_MULTI_SELECT
            field.choice_values = [('A', 'Alpha'), ('B', 'Beta'), ('C', 'Gamma')]
            field.field_value = 'A'
            field.rect = pdf.Rect(40, 100, 300, 220)
            refs.append(page.add_widget(field).xref)
        parent = document.get_new_xref()
        document.update_object(parent, '<</FT /Ch /Ff 2097152 /T (shared) /Opt [[(A)(Alpha)][(B)(Beta)][(C)(Gamma)]] '
                               '/V [(A)] /I [0] /Kids [' + ' '.join(f'{xref} 0 R' for xref in refs) + ']>>')
        for xref in refs:
            obj = document.xref_object(xref)
            # The widget contains only its rectangle and appearance; logical
            # choice data belongs to the named parent field.
            for key in ('FT', 'T', 'V', 'I', 'Opt', 'Ff'):
                obj = re.sub(r'/' + key + r'\s+(?:\[.*?\]|\(.*?\)|/\w+|\d+)\n', '', obj, flags=re.S)
            document.update_object(xref, obj)
            document.xref_set_key(xref, 'Parent', f'{parent} 0 R')
        document.xref_set_key(document.pdf_catalog(), 'AcroForm/Fields', f'[{parent} 0 R]')
        document.save(path)


@pytest.mark.parametrize('selected', (['B', 'C'], []))
def test_shared_multiselect_updates_canonical_parent_and_all_appearances(tmp_path, selected):
    source, target = tmp_path / 'source.pdf', tmp_path / 'filled.pdf'
    shared_choice_fixture(source)
    with pdf.open(source) as document:
        page = document[0]
        field = next(page.widgets())
        key = str(field.xref)
        assert choice_selection(field) == ['A']
        assert choice_options(field) == [('A', 'Alpha'), ('B', 'Beta'), ('C', 'Gamma')]
        before = [document.xref_stream(int(document.xref_get_key(next(page.widgets()).xref, 'AP/N')[1].split()[0]))
                  for page in document]
    transform(source, target, 'fill_forms', form_values={key: selected})
    fields, widgets = canonical(target)
    assert fields['shared']['/V'] == selected
    parent = widgets[0]['/Parent'].get_object()
    assert parent['/I'] == [1, 2] if selected else isinstance(parent['/I'], NullObject)
    assert all('/V' not in widget for widget in widgets)
    with pdf.open(target) as document:
        for index, page in enumerate(document):
            field = next(page.widgets())
            assert choice_selection(field) == selected
            assert choice_options(field) == [('A', 'Alpha'), ('B', 'Beta'), ('C', 'Gamma')]
            stream = document.xref_stream(int(document.xref_get_key(field.xref, 'AP/N')[1].split()[0]))
            assert stream != before[index]
            page.get_pixmap(matrix=pdf.Matrix(1.5, 1.5)).save(tmp_path / f'choice-{index}.png')


def test_readonly_shared_choice_is_locked_on_every_page(tmp_path):
    app = QApplication.instance() or QApplication([])
    source, readonly, target = (tmp_path / name for name in ('source.pdf', 'readonly.pdf', 'out.pdf'))
    shared_choice_fixture(source)
    with pdf.open(source) as document:
        key = str(next(document[0].widgets()).xref)
        widget = next(document[1].widgets())
        document.xref_set_key(widget.xref, 'Ff', str(pdf.PDF_CH_FIELD_IS_MULTI_SELECT | pdf.PDF_FIELD_IS_READ_ONLY))
        document.save(readonly)
    dialog = FormDialog(readonly, 0)
    try:
        assert not dialog.fields
        editor = dialog.findChild(QListWidget)
        assert not editor.isEnabled()
        assert [editor.item(index).text() for index in range(editor.count())] == ['Alpha', 'Beta', 'Gamma']
        with pytest.raises(ValueError, match='읽기 전용'):
            transform(readonly, target, 'fill_forms', form_values={key: ['B', 'C']})
        assert not target.exists()
    finally:
        dialog.close()
        app.processEvents()


@pytest.mark.parametrize('rotation', (0, 90, 180, 270))
def test_many_office_table_cells_and_merged_note_keep_correct_positions(tmp_path, rotation):
    source, target = tmp_path / 'table.pdf', tmp_path / 'form.pdf'
    with pdf.open() as document:
        page = document.new_page(width=650, height=1700)
        # 32 narrow rows and a merged notes region, all with shared borders.
        page.draw_rect(pdf.Rect(70, 90, 550, 1114))
        page.draw_line((210, 90), (210, 1114))
        for row in range(32):
            y = 90 + row * 32
            if row:
                page.draw_line((70, y), (550, y))
            page.insert_text((85, y + 21), f'Label {row + 1}')
        page.draw_rect(pdf.Rect(70, 1170, 550, 1370))
        page.draw_line((210, 1170), (210, 1370))
        page.draw_line((70, 1270), (210, 1270))
        page.insert_text((85, 1210), 'Notes')
        page.insert_text((85, 1310), 'Details')
        page.set_cropbox(pdf.Rect(30, 50, 630, 1650))
        page.set_rotation(rotation)
        document.save(source)
    original = source.read_bytes()
    assert transform(source, target, 'auto_forms') == 33
    with pdf.open(target) as document:
        page = document[0]
        fields = list(page.widgets())
        assert len(fields) == 33
        assert tuple(fields[-1].rect) == (180, 1120, 520, 1320)
        assert fields[-1].field_flags & pdf.PDF_TX_FIELD_IS_MULTILINE
        assert [tuple(field.rect) for field in fields[:32]] == [
            (180, 40 + row * 32, 520, 72 + row * 32) for row in range(32)]
        assert page.rotation == rotation
        assert candidates(page) == []
        values = {str(field.xref): f'Row {index}' for index, field in enumerate(fields)}
    filled = tmp_path / 'filled.pdf'
    transform(target, filled, 'fill_forms', form_values=values)
    reader = PdfReader(filled)
    assert len(reader.get_fields()) == 33
    assert {field['/V'] for field in reader.get_fields().values()} == {f'Row {index}' for index in range(33)}
    assert source.read_bytes() == original
