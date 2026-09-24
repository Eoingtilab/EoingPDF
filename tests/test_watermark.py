import hashlib
import math
import sys
from pathlib import Path
import pymupdf as pdf
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'source.pdf'
    with pdf.open() as doc:
        for rotation in (0, 90):
            page = doc.new_page(width=600, height=400)
            page.insert_text((30, 40), 'Original body')
            page.set_rotation(rotation)
        doc.save(path)
    return path


def test_diagonal_text_on_rotated_and_normal_pages(source, tmp_path):
    before = hashlib.sha256(source.read_bytes()).digest()
    target = tmp_path / 'marked.pdf'
    transform(source, target, 'watermark_text', watermark_text='CONFIDENTIAL', watermark_opacity=.25)
    assert hashlib.sha256(source.read_bytes()).digest() == before
    with pdf.open(target) as doc:
        for page in doc:
            assert 'Original body' in page.get_text()
            assert 'CONFIDENTIAL' in page.get_text()
            lines = [line for block in page.get_text('dict')['blocks'] if 'lines' in block
                     for line in block['lines'] if any('CONFIDENTIAL' in span['text'] for span in line['spans'])]
            assert len(lines) == 1
            dx, dy = lines[0]['dir']
            rotation = pdf.Matrix(page.rotation_matrix)
            rotation.e = rotation.f = 0
            dx, dy = pdf.Point(dx, dy) * rotation
            assert abs(abs(math.degrees(math.atan2(dy, dx))) - 45) < .1


def test_png_alpha_and_original_preserved(source, tmp_path):
    png, target = tmp_path / 'mark.png', tmp_path / 'marked.pdf'
    image = Image.new('RGBA', (100, 100), (255, 0, 0, 0))
    for x in range(25, 75):
        for y in range(25, 75):
            image.putpixel((x, y), (255, 0, 0, 255))
    image.save(png)
    transform(source, target, 'watermark_png', watermark_image=str(png), watermark_opacity=.5)
    with pdf.open(target) as doc:
        page = doc[0]
        raster = page.get_pixmap()
        center = raster.pixel(300, 200)
        assert center[0] >= 250 and 120 <= center[1] <= 135
        assert raster.pixel(190, 90) == (255, 255, 255)
        assert 'Original body' in page.get_text()


@pytest.mark.parametrize('opacity', [0, -1, float('nan'), 1.1])
def test_invalid_opacity_does_not_publish(source, tmp_path, opacity):
    target = tmp_path / 'invalid.pdf'
    with pytest.raises(ValueError):
        transform(source, target, 'watermark_text', watermark_text='TEST', watermark_opacity=opacity)
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))
