import sys
import io
from pathlib import Path
import pymupdf as pdf
import pytest
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.page_edits import apply_page_order


@pytest.mark.parametrize('order', ([0, 1, 2], [2, 0, 1], [2, 0]))
@pytest.mark.parametrize('encrypted', (False, True))
def test_field_tree_matches_retained_widgets_and_page_order(tmp_path, order, encrypted):
    source, target = tmp_path / 'source.pdf', tmp_path / 'output.pdf'
    with pdf.open() as document:
        for index in range(3):
            page = document.new_page()
            page.insert_text((40, 100), f'PAGE {index}')
            widget = pdf.Widget()
            widget.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            widget.field_name = f'name{index}'
            widget.field_value = f'VALUE {index}'
            widget.rect = pdf.Rect(40, 150, 240, 180)
            page.add_widget(widget)
        options = dict(encryption=pdf.PDF_ENCRYPT_AES_256, user_pw='secret', owner_pw='owner') if encrypted else {}
        document.save(source, **options)
    original = source.read_bytes()
    with pdf.open(source) as document:
        if encrypted:
            assert document.authenticate('secret')
        apply_page_order(document, order)
        document.save(target, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_KEEP)
    with pdf.open(target) as document:
        if encrypted:
            assert document.needs_pass and document.authenticate('secret')
        # Verify canonical fields with an independent reader after decrypting
        # in memory; the saved encrypted file itself is never rewritten.
        reader = PdfReader(io.BytesIO(document.tobytes(encryption=pdf.PDF_ENCRYPT_NONE)))
    fields = reader.get_fields()
    assert {name: field['/V'] for name, field in fields.items()} == {f'name{i}': f'VALUE {i}' for i in order}
    with pdf.open(target) as document:
        if encrypted:
            document.authenticate('secret')
        assert [next(page.widgets()).field_name for page in document] == [f'name{i}' for i in order]
    assert source.read_bytes() == original
