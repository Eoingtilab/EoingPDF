import sys
from pathlib import Path
from unittest.mock import patch
import pymupdf as pdf
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('operation', ['searchable', 'watermark_text', 'watermark_png'])
def test_overlays_keep_crop_and_rotation(tmp_path, rotation, operation):
    source, target = tmp_path / 'source.pdf', tmp_path / 'result.pdf'
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.draw_rect(page.rect, fill=(1, 0, 0), color=None)
        page.draw_rect(pdf.Rect(80, 100, 520, 700), fill=(1, 1, 1), color=None)
        page.set_cropbox(pdf.Rect(100, 120, 500, 680))
        page.set_rotation(rotation)
        dimensions = (page.rect.width, page.rect.height)
        document.save(source)
    original = source.read_bytes()
    mark = tmp_path / 'mark.png'
    Image.new('RGBA', (60, 30), (0, 0, 255, 255)).save(mark)
    layout = {'width': dimensions[0], 'height': dimensions[1], 'lines': [
        {'text': 'SCAN', 'words': [{'text': 'SCAN', 'box': [50, 60, 100, 25]}]}]}
    with patch('eoingpdf.ocr.page_layout', return_value=layout):
        transform(source, target, operation, watermark_text='CONFIDENTIAL', watermark_image=str(mark))
    with pdf.open(source) as before, pdf.open(target) as after:
        page = after[0]
        assert page.cropbox == before[0].cropbox
        assert page.rotation == rotation and page.rect == before[0].rect
        raster = page.get_pixmap(colorspace=pdf.csRGB)
        samples = raster.samples
        colors = set(samples[i:i+3] for i in range(0, len(samples), 3))
        assert b'\xff\x00\x00' not in colors
        if operation == 'searchable':
            assert raster.samples == before[0].get_pixmap(colorspace=pdf.csRGB).samples
            box = page.search_for('SCAN')[0] * page.rotation_matrix
            assert abs(box.x0 - 50) < 1 and abs(box.y0 - 60) < 1
            assert abs(box.x1 - 150) < 1 and abs(box.y1 - 85) < 1
        elif operation == 'watermark_text':
            assert 'CONFIDENTIAL' in page.get_text()
        else:
            pixel = raster.pixel(raster.width // 2, raster.height // 2)
            assert pixel[2] > pixel[0]
    assert source.read_bytes() == original
