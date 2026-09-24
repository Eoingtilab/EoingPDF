import hashlib
import io
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
import pytest
from PIL import Image, ImageDraw
from eoingpdf.advanced import transform
from eoingpdf.stamping import prepare_image
from eoingpdf.core import Cancelled


@pytest.fixture
def seal(tmp_path):
    path = tmp_path / 'seal.png'
    image = Image.new('RGB', (120, 120), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 109, 109), outline='red', width=10)
    draw.line((25, 50, 95, 50), fill='red', width=8)
    image.save(path)
    return path


def document(path, rotation=0):
    with pdf.open() as doc:
        for _ in range(2):
            page = doc.new_page(width=340, height=320)
            page.draw_rect(page.rect, color=None, fill=(.7, .8, .9))
            page.insert_text((80, 200), 'Original searchable text')
            page.set_cropbox(pdf.Rect(20, 20, 320, 300))
            page.set_rotation(rotation)
        doc.save(path)


@pytest.mark.parametrize('rotation', (0, 90, 180, 270))
def test_display_position_crop_knockout_and_untouched_page(tmp_path, seal, rotation):
    source, target = tmp_path / 'source.pdf', tmp_path / 'result.pdf'
    document(source, rotation)
    before = hashlib.sha256(source.read_bytes()).digest()
    transform(source, target, 'stamp', watermark_image=str(seal), stamp_pages='1',
              stamp_x_mm=25.4, stamp_y_mm=25.4, stamp_width_mm=25.4, stamp_flatten=False)
    with pdf.open(source) as original, pdf.open(target) as result:
        assert result[0].rotation == rotation and result[0].cropbox == original[0].cropbox
        raster = result[0].get_pixmap()
        assert raster.pixel(74, 74)[0] > 240 and raster.pixel(74, 74)[1] < 30
        assert raster.pixel(110, 125) == original[0].get_pixmap().pixel(110, 125)
        assert result[1].get_pixmap().samples == original[1].get_pixmap().samples
        assert 'Original searchable text' in result[0].get_text()
    assert hashlib.sha256(source.read_bytes()).digest() == before


def test_flatten_resolution_and_no_separate_stamp(tmp_path, seal):
    source, target = tmp_path / 'source.pdf', tmp_path / 'flat.pdf'
    document(source, 90)
    transform(source, target, 'stamp', watermark_image=str(seal), stamp_pages='1-end')
    with pdf.open(target) as result:
        assert len(result) == 2
        for page in result:
            assert not page.get_text().strip()
            images = page.get_images()
            assert len(images) == 1
            assert abs(images[0][2] / page.rect.width * 72 - 300) < 1
            assert abs(images[0][3] / page.rect.height * 72 - 300) < 1


@pytest.mark.parametrize('options', ({'stamp_x_mm': float('nan')}, {'stamp_width_mm': 0},
    {'stamp_y_mm': -1}, {'stamp_x_mm': 500}, {'stamp_pages': '99'}, {'cancelled': lambda: True}))
def test_invalid_or_cancel_has_no_output(tmp_path, seal, options):
    source, target = tmp_path / 'source.pdf', tmp_path / 'failed.pdf'
    document(source)
    with pytest.raises((ValueError, Cancelled)):
        transform(source, target, 'stamp', watermark_image=str(seal), **options)
    assert not target.exists() and not list(tmp_path.glob('.eoing-*'))


def test_empty_image_and_existing_alpha(tmp_path):
    path = tmp_path / 'empty.png'
    Image.new('RGB', (20, 20), 'white').save(path)
    with pytest.raises(ValueError, match='남는'):
        prepare_image(path)
    image = Image.new('RGBA', (20, 20), (255, 0, 0, 128))
    image.save(path)
    stream, aspect = prepare_image(path)
    with Image.open(io.BytesIO(stream)) as processed:
        assert processed.getpixel((10, 10)) == (255, 0, 0, 128)
        assert aspect == 1
