import sys
from pathlib import Path
import pymupdf as pdf
import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform


def pixels(page):
    raster = page.get_pixmap(colorspace=pdf.csRGB, alpha=False)
    return np.frombuffer(raster.samples, dtype=np.uint8).reshape(raster.height, raster.width, 3)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('cropped', [False, True])
def test_split_matches_visible_halves_with_annotations(tmp_path, rotation, cropped):
    source, target = tmp_path / 'spread.pdf', tmp_path / 'split.pdf'
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.draw_rect(pdf.Rect(0, 0, 300, 800), fill=(.1, .3, .8), color=None)
        page.draw_rect(pdf.Rect(300, 0, 600, 800), fill=(.8, .3, .1), color=None)
        page.insert_text((80, 160), 'Left text', fontsize=20)
        page.insert_text((380, 550), 'Right text', fontsize=20)
        note = page.add_rect_annot(pdf.Rect(150, 300, 450, 450))
        note.set_colors(fill=(0, 1, 0), stroke=(0, 1, 0))
        note.update()
        if cropped:
            page.set_cropbox(pdf.Rect(40, 60, 560, 740))
        page.set_rotation(rotation)
        document.save(source)
    before = source.read_bytes()
    with pdf.open(source) as document:
        expected = pixels(document[0]).copy()
    transform(source, target, 'split_spread')
    with pdf.open(target) as document:
        assert len(document) == 2
        actual = np.concatenate([pixels(page) for page in document], axis=1)
        assert actual.shape == expected.shape
        # Normalizing PDF transforms can change antialiasing at edge pixels.
        difference = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
        assert float(np.mean(difference)) < .5
        assert float(np.mean(np.max(difference, axis=2) > 20)) < .01
        assert all(page.get_drawings() for page in document)
        assert any('text' in page.get_text() for page in document)
    assert source.read_bytes() == before


def test_empty_and_odd_width_pages(tmp_path):
    source, target = tmp_path / 'empty.pdf', tmp_path / 'split.pdf'
    with pdf.open() as document:
        document.new_page(width=601, height=400)
        document.save(source)
    transform(source, target, 'split_spread')
    with pdf.open(target) as document:
        assert len(document) == 2
        assert all(page.rect.width == 300.5 for page in document)
