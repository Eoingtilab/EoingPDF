import sys
from pathlib import Path
import pymupdf as pdf
import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.roll_layout import slice_boundaries


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_stitch_visible_pages_without_gaps(tmp_path, rotation):
    source, target = tmp_path / 'source.pdf', tmp_path / 'roll.pdf'
    with pdf.open() as document:
        for index in range(2):
            page = document.new_page(width=600, height=800)
            page.draw_rect(page.rect, fill=(1, 0, 0), color=None)
            page.draw_rect(pdf.Rect(100, 100, 500, 700), fill=(.1 * index, .4, .8), color=None)
            page.insert_text((150, 200), f'Page {index + 1}')
            page.set_cropbox(pdf.Rect(120, 120, 480, 680))
            page.set_rotation(rotation)
        document.save(source)
    before = source.read_bytes()
    with pdf.open(source) as document:
        rasters = [page.get_pixmap(colorspace=pdf.csRGB) for page in document]
        expected = np.concatenate([np.frombuffer(r.samples, dtype=np.uint8).reshape(r.height, r.width, 3)
                                   for r in rasters], axis=0)
    transform(source, target, 'stitch')
    with pdf.open(target) as document:
        assert len(document) == 1
        raster = document[0].get_pixmap(colorspace=pdf.csRGB)
        actual = np.frombuffer(raster.samples, dtype=np.uint8).reshape(raster.height, raster.width, 3)
        assert actual.shape == expected.shape
        assert np.abs(actual.astype(int) - expected.astype(int)).mean() < .5
        assert document[0].get_text().find('Page 1') < document[0].get_text().find('Page 2')
    assert source.read_bytes() == before


def test_mixed_widths_and_height_limit(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'roll.pdf'
    with pdf.open() as document:
        document.new_page(width=100, height=100)
        document.new_page(width=200, height=100)
        document.save(source)
    transform(source, target, 'stitch')
    with pdf.open(target) as document:
        assert document[0].rect == pdf.Rect(0, 0, 200, 300)
    huge = tmp_path / 'huge.pdf'
    with pdf.open() as document:
        document.new_page(width=100, height=10000)
        document.new_page(width=100, height=10000)
        document.save(huge)
    rejected = tmp_path / 'rejected.pdf'
    with pytest.raises(ValueError, match='14,400'):
        transform(huge, rejected, 'stitch')
    assert not rejected.exists() and not list(tmp_path.glob('.eoing-*'))


def test_slice_uses_whitespace_and_keeps_all_text(tmp_path):
    source, target = tmp_path / 'long.pdf', tmp_path / 'a4.pdf'
    with pdf.open() as document:
        page = document.new_page(width=500, height=1500)
        for y, text in [(100, 'First paragraph'), (600, 'Second paragraph'), (1100, 'Third paragraph')]:
            page.insert_text((40, y), text, fontsize=24)
        cuts = slice_boundaries(page)
        assert cuts[0] == 0 and cuts[-1] == 1500
        for cut in cuts[1:-1]:
            assert all(not block[1] <= cut <= block[3] for block in page.get_text('blocks'))
        document.save(source)
    before = source.read_bytes()
    transform(source, target, 'slice_a4')
    with pdf.open(target) as document:
        assert len(document) >= 2
        text = '\n'.join(page.get_text() for page in document)
        for word in ('First paragraph', 'Second paragraph', 'Third paragraph'):
            assert text.count(word) == 1
        assert all(page.rect == pdf.Rect(0, 0, 595, 842) for page in document)
    assert source.read_bytes() == before


def test_unsplittable_picture_is_scaled_without_cut(tmp_path):
    source, target = tmp_path / 'picture.pdf', tmp_path / 'a4.pdf'
    with pdf.open() as document:
        page = document.new_page(width=300, height=1500)
        page.draw_rect(page.rect, fill=(0, 0, 1), color=None)
        assert slice_boundaries(page) == [0, 1500]
        document.save(source)
    transform(source, target, 'slice_a4')
    with pdf.open(target) as document:
        assert len(document) == 1
        rect = document[0].get_drawings()[0]['rect']
        assert abs(rect.height - 842) < 1
        assert document[0].rect.contains(rect)
