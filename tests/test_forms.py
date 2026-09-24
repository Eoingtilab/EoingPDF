import sys
from pathlib import Path
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled


def fixture(path, rotation=0):
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.draw_rect(pdf.Rect(80, 100, 300, 130))
        page.draw_rect(pdf.Rect(80, 180, 96, 196))
        page.draw_line((80, 250), (300, 250))
        page.insert_text((80, 320), '__________')
        page.draw_rect(pdf.Rect(80, 380, 300, 410))
        page.insert_text((100, 400), 'Already filled')
        page.set_rotation(rotation)
        document.save(path)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_real_fields_idempotent_and_fillable(tmp_path, rotation):
    source, target = tmp_path / 'form.pdf', tmp_path / 'fillable.pdf'
    fixture(source, rotation)
    original = source.read_bytes()
    assert transform(source, target, 'auto_forms') == 4
    filled = tmp_path / 'filled.pdf'
    with pdf.open(target) as document:
        page = document[0]
        fields = list(page.widgets())
        assert len(fields) == 4
        assert sum(widget.field_type == pdf.PDF_WIDGET_TYPE_CHECKBOX for widget in fields) == 1
        assert page.rotation == rotation
        for widget in fields:
            widget.field_value = widget.on_state() if widget.field_type == pdf.PDF_WIDGET_TYPE_CHECKBOX else 'Alice'
            widget.update()
        document.save(filled)
    with pdf.open(filled) as document:
        assert all(widget.field_value in ('Alice', 'Yes') for widget in document[0].widgets())
    repeated = tmp_path / 'repeated.pdf'
    assert transform(target, repeated, 'auto_forms') == 0
    with pdf.open(repeated) as document:
        assert len(list(document[0].widgets())) == 4
    assert source.read_bytes() == original


def test_empty_and_cancel_dont_publish(tmp_path):
    source, target = tmp_path / 'blank.pdf', tmp_path / 'out.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    with pytest.raises(ValueError, match='찾지 못했습니다'):
        transform(source, target, 'auto_forms')
    with pytest.raises(Cancelled):
        transform(source, target, 'auto_forms', cancelled=lambda: True)
    assert not target.exists() and not list(tmp_path.glob('.eoing-*'))


def test_text_brackets_detected(tmp_path):
    source, target = tmp_path / 'brackets.pdf', tmp_path / 'out.pdf'
    with pdf.open() as document:
        page = document.new_page()
        page.insert_text((60, 100), '[   ] Accept', fontsize=14)
        document.save(source)
    transform(source, target, 'auto_forms')
    with pdf.open(target) as document:
        page = document[0]
        fields = list(page.widgets())
        assert len(fields) == 1 and fields[0].field_type == pdf.PDF_WIDGET_TYPE_CHECKBOX


def test_fill_korean_round_trip_and_reject_unknown_field(tmp_path):
    source, form, target = tmp_path / 'source.pdf', tmp_path / 'form.pdf', tmp_path / 'filled.pdf'
    fixture(source)
    transform(source, form, 'auto_forms')
    with pdf.open(form) as document:
        page = document[0]
        key = str(next(field for field in page.widgets() if field.field_type == pdf.PDF_WIDGET_TYPE_TEXT).xref)
    original = form.read_bytes()
    transform(form, target, 'fill_forms', form_values={key: '홍길동'})
    with pdf.open(target) as document:
        page = document[0]
        assert '홍길동' in page.get_text()
        assert any(field.field_value == '홍길동' for field in page.widgets())
    assert form.read_bytes() == original
    rejected = tmp_path / 'unknown.pdf'
    with pytest.raises(ValueError, match='다시 열어'):
        transform(form, rejected, 'fill_forms', form_values={'999999': 'value'})
    assert not rejected.exists()
