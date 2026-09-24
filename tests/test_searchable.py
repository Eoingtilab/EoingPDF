import sys
from pathlib import Path
from unittest.mock import patch
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.ocr import page_layout


def scanned_pdf(path, text='HELLO WORLD 123456'):
    with pdf.open() as vector, pdf.open() as scan:
        page = vector.new_page(width=600, height=200)
        page.insert_text((50, 80), text, fontsize=28)
        raster = page.get_pixmap(matrix=pdf.Matrix(2, 2), alpha=False)
        page = scan.new_page(width=600, height=200)
        page.insert_image(page.rect, stream=raster.tobytes('png'))
        scan.save(path)


def test_transparent_layer_keeps_pixels_and_positions(tmp_path):
    source, target = tmp_path / 'scan.pdf', tmp_path / 'searchable.pdf'
    scanned_pdf(source)
    layout = {'width': 600, 'height': 200, 'lines': [
        {'text': 'HELLO', 'words': [{'text': 'HELLO', 'box': [50, 52, 90, 28]}]}]}
    with patch('eoingpdf.ocr.page_layout', return_value=layout):
        transform(source, target, 'searchable')
    with pdf.open(source) as original, pdf.open(target) as result:
        assert original[0].get_pixmap().samples == result[0].get_pixmap().samples
        box = result[0].search_for('HELLO')[0]
        assert abs(box.x0 - 50) < 1
        assert abs(box.x1 - 140) < 1
        assert abs(box.y0 - 52) < 1
        assert abs(box.y1 - 80) < 1


def test_scanned_email_pixels_and_text_removed(tmp_path):
    source, target = tmp_path / 'email.pdf', tmp_path / 'safe.pdf'
    scanned_pdf(source, 'person@example.com')
    original_bytes = source.read_bytes()
    layout = {'width': 600, 'height': 200, 'lines': [
        {'text': 'person@example.com', 'words': [{'text': 'person@example.com', 'box': [50, 50, 300, 35]}]}]}
    with patch('eoingpdf.ocr.page_layout', return_value=layout):
        transform(source, target, 'ocr_redact')
    assert source.read_bytes() == original_bytes
    with pdf.open(target) as doc:
        assert 'person@example.com' not in doc[0].get_text()
        raster = doc[0].get_pixmap()
        assert raster.pixel(100, 65) == (0, 0, 0)
        assert raster.pixel(400, 150) == (255, 255, 255)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows OCR integration')
def test_real_windows_ocr_words_and_searchable_pdf(tmp_path):
    source, target = tmp_path / 'scan.pdf', tmp_path / 'searchable.pdf'
    scanned_pdf(source)
    with pdf.open(source) as doc:
        result = page_layout(doc[0])
        assert result['width'] > 0
        assert 'HELLO' in ' '.join(line['text'] for line in result['lines']).upper()
        assert all(len(word['box']) == 4 for line in result['lines'] for word in line['words'])
    transform(source, target, 'searchable')
    with pdf.open(target) as doc:
        assert 'HELLO' in doc[0].get_text().upper()
