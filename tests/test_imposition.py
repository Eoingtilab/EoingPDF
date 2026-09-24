import sys
from pathlib import Path
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.imposition import sheet_order
from eoingpdf.core import Cancelled


def source_pdf(path, count):
    with pdf.open() as document:
        for index in range(count):
            page = document.new_page(width=400, height=600)
            page.insert_text((40, 80), f'Page {index + 1}')
            page.draw_rect(pdf.Rect(40, 100, 120, 150), fill=(0, 0, 1))
        document.save(path)


def test_booklet_order_and_padding():
    assert sheet_order(8, 'booklet') == [[7, 0], [1, 6], [5, 2], [3, 4]]
    assert sheet_order(5, 'booklet') == [[None, 0], [1, None], [None, 2], [3, 4]]
    assert sheet_order(1, 'booklet') == [[None, 0], [None, None]]
    for count in range(1, 101):
        order = sheet_order(count, 'booklet')
        assert sorted(index for pair in order for index in pair if index is not None) == list(range(count))


@pytest.mark.parametrize('mode', ['four_up', 'booklet'])
def test_layout_text_vector_and_original(tmp_path, mode):
    source, target = tmp_path / 'source.pdf', tmp_path / 'result.pdf'
    source_pdf(source, 5)
    original = source.read_bytes()
    transform(source, target, mode)
    with pdf.open(target) as document:
        expected = sheet_order(5, mode)
        assert len(document) == len(expected)
        for page, indices in zip(document, expected):
            assert tuple(page.rect) == (0, 0, 842, 595)
            assert page.get_text().splitlines() == [f'Page {index + 1}' for index in indices if index is not None]
            assert page.get_drawings()
            words = page.get_text('words')
            assert all(page.rect.contains(pdf.Rect(word[:4])) for word in words)
    assert source.read_bytes() == original


def test_rotated_page_annotations_are_printable(tmp_path):
    source, target = tmp_path / 'annotated.pdf', tmp_path / 'out.pdf'
    with pdf.open() as document:
        page = document.new_page(width=400, height=600)
        page.insert_text((40, 100), 'Rotated content')
        annotation = page.add_rect_annot(pdf.Rect(40, 140, 140, 200))
        annotation.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
        annotation.update()
        page.set_rotation(90)
        document.save(source)
    transform(source, target, 'four_up')
    with pdf.open(target) as document:
        assert 'Rotated content' in document[0].get_text()
        assert any(item.get('fill') == (1, 0, 0) for item in document[0].get_drawings())
        assert not list(document[0].annots() or ())


def test_cancel_does_not_publish(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    source_pdf(source, 5)
    state = {'stop': False}
    def progress(value):
        state['stop'] = True
    with pytest.raises(Cancelled):
        transform(source, target, 'booklet', cancelled=lambda: state['stop'], progress=progress)
    assert not target.exists() and not list(tmp_path.glob('.eoing-*'))


@pytest.mark.parametrize('rotation', [90, 180, 270])
def test_cropped_rotated_page_does_not_reveal_hidden_margins(tmp_path, rotation):
    source, target = tmp_path / 'cropped.pdf', tmp_path / 'out.pdf'
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.draw_rect(page.rect, fill=(1, 0, 0), color=None)
        page.draw_rect(pdf.Rect(100, 100, 500, 700), fill=(0, 0, 1), color=None)
        page.set_cropbox(pdf.Rect(120, 120, 480, 680))
        page.set_rotation(rotation)
        document.save(source)
    transform(source, target, 'four_up')
    with pdf.open(target) as document:
        raw = document[0].get_pixmap(colorspace=pdf.csRGB).samples
        colors = set(raw[i:i+3] for i in range(0, len(raw), 3))
        assert b'\x00\x00\xff' in colors
        assert b'\xff\x00\x00' not in colors
