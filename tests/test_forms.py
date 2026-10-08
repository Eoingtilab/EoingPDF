import sys
from pathlib import Path
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled
from eoingpdf.forms import candidates


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


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('border_kind', ['stroke', 'filled'])
def test_shared_table_borders_detect_empty_cells_without_row_wide_fields(tmp_path, rotation, border_kind):
    source, target = tmp_path / 'table.pdf', tmp_path / 'fillable.pdf'
    with pdf.open() as document:
        page = document.new_page(width=650, height=850)
        if border_kind == 'stroke':
            page.draw_rect(pdf.Rect(70, 90, 530, 210))
            page.draw_line((210, 90), (210, 210))
            for y in (130, 170):
                page.draw_line((70, y), (530, y))
        else:
            # Word exports borders as short, filled strips rather than strokes.
            for x in (70, 210, 530):
                for y in (90, 130, 170):
                    page.draw_rect(pdf.Rect(x - .25, y, x + .25, y + 40), color=None, fill=(0, 0, 0))
            for y in (90, 130, 170, 210):
                for x0, x1 in ((70, 210), (210, 530)):
                    page.draw_rect(pdf.Rect(x0, y - .25, x1, y + .25), color=None, fill=(0, 0, 0))
        for y in (115, 155, 195):
            page.insert_text((90, y), 'Label')
        page.set_cropbox(pdf.Rect(30, 50, 630, 850))
        page.set_rotation(rotation)
        document.save(source)
    original = source.read_bytes()
    expected = [(180, 40, 500, 80), (180, 80, 500, 120), (180, 120, 500, 160)]
    assert transform(source, target, 'auto_forms') == 3
    with pdf.open(target) as document:
        page = document[0]
        fields = list(page.widgets())
        assert [tuple(field.rect) for field in fields] == expected
        assert page.rotation == rotation
        assert page.cropbox == pdf.Rect(30, 50, 630, 850)
        assert candidates(page) == []
        key = str(fields[1].xref)
    filled = tmp_path / 'filled.pdf'
    transform(target, filled, 'fill_forms', form_values={key: '홍길동'})
    with pdf.open(filled) as document:
        assert '홍길동' in document[0].get_text()
        assert any(field.field_value == '홍길동' for field in document[0].widgets())
    assert source.read_bytes() == original


def test_four_line_boxes_and_merged_cells_keep_text_and_existing_fields_out(tmp_path):
    source, target = tmp_path / 'paths.pdf', tmp_path / 'fillable.pdf'
    with pdf.open() as document:
        page = document.new_page()
        shape = page.new_shape()
        for first, last in [((40, 40), (240, 40)), ((240, 40), (240, 70)),
                            ((240, 70), (40, 70)), ((40, 70), (40, 40))]:
            shape.draw_line(first, last)
        shape.finish()
        shape.commit()
        # The right-hand column is a merged cell spanning two rows.
        page.draw_rect(pdf.Rect(40, 120, 500, 200))
        page.draw_line((180, 120), (180, 200))
        page.draw_line((40, 160), (180, 160))
        page.insert_text((60, 145), 'Label')
        field = pdf.Widget()
        field.field_name, field.field_type = 'existing', pdf.PDF_WIDGET_TYPE_TEXT
        field.rect = pdf.Rect(40, 160, 180, 200)
        page.add_widget(field)
        document.save(source)
    assert transform(source, target, 'auto_forms') == 2
    with pdf.open(target) as document:
        fields = list(document[0].widgets())
        assert len(fields) == 3
        assert {tuple(field.rect) for field in fields if field.field_name != 'existing'} == {
            (40, 40, 240, 70), (180, 120, 500, 200)}
        assert sum(field.field_name == 'existing' for field in fields) == 1


def test_filled_underline_is_detected_without_treating_solid_boxes_as_fields(tmp_path):
    source, target = tmp_path / 'filled-lines.pdf', tmp_path / 'form.pdf'
    with pdf.open() as document:
        page = document.new_page()
        page.draw_rect(pdf.Rect(40, 80, 250, 81), color=None, fill=(0, 0, 0))
        page.draw_rect(pdf.Rect(40, 120, 250, 150), color=None, fill=(0, 0, 0))
        document.save(source)
    assert transform(source, target, 'auto_forms') == 1
    with pdf.open(target) as document:
        page = document[0]
        fields = list(page.widgets())
        assert len(fields) == 1 and tuple(fields[0].rect) == (40, 64.5, 250, 80.5)
