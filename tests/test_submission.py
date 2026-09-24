import io
from pathlib import Path
import sys

import numpy as np
import pymupdf as pdf
import pytest
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled
from eoingpdf.imaging import remove_shadows
from eoingpdf.submission import sensitive_regions


def test_shadow_correction_keeps_ink_and_flattens_paper():
    gray = np.tile(np.linspace(140, 245, 600).astype(np.uint8), (300, 1))
    gray[140:147, 100:500] = 15
    result = remove_shadows(gray)
    assert result[50, 50] > 240 and result[50, 550] > 240
    assert result[143, 300] < 35
    assert np.ptp(result[50, 50:550]) < 12


def test_split_ocr_tokens_are_masked_without_unrelated_words():
    with pdf.open() as document:
        page = document.new_page(width=200, height=100)
        layout = {'width': 400, 'height': 200, 'lines': [{'words': [
            {'text': 'Tel', 'box': [0, 10, 20, 20]},
            {'text': '010-', 'box': [40, 10, 40, 20]},
            {'text': '1234-', 'box': [80, 10, 50, 20]},
            {'text': '5678', 'box': [130, 10, 40, 20]},
        ]}]}
        rectangles = sensitive_regions(layout, page)
        assert len(rectangles) == 3
        assert min(rect[0] for rect in rectangles) == 19
        assert max(rect[2] for rect in rectangles) == 86
        layout['lines'][0]['words'][0]['box'][0] = float('nan')
        with pytest.raises(ValueError):
            sensitive_regions(layout, page)


def scan_fixture(path):
    stream = io.BytesIO()
    image = Image.new('RGB', (400, 200), 'white')
    ImageDraw.Draw(image).rectangle((40, 40, 240, 64), fill='blue')
    image.save(stream, format='PNG')
    with pdf.open() as document:
        page = document.new_page(width=200, height=100)
        page.insert_image(page.rect, stream=stream.getvalue())
        page.insert_text((15, 75), 'native@example.com', fontsize=10)
        document.set_metadata({'author': 'PRIVATE AUTHOR'})
        document.save(path)


def test_submission_masks_pixels_and_native_text_preserving_source(tmp_path, monkeypatch):
    source, target = tmp_path / 'source.pdf', tmp_path / 'result.pdf'
    scan_fixture(source)
    original = source.read_bytes()
    monkeypatch.setattr('eoingpdf.ocr.page_layout', lambda page, cancelled: {
        'width': 200, 'height': 100, 'lines': [{'words': [
            {'text': '010-1234-5678', 'box': [20, 20, 100, 12]}]}]})
    assert transform(source, target, 'safe_submission') >= 2
    assert source.read_bytes() == original
    with pdf.open(target) as document:
        assert len(document) == 1
        page = document[0]
        assert not page.get_text().strip()
        assert not document.metadata.get('author')
        raster = page.get_pixmap()
        assert raster.pixel(50, 25) == (0, 0, 0)
        assert raster.pixel(150, 25) == (255, 255, 255)
        # The surviving image itself must be redacted, not just covered on-screen.
        for image in page.get_images(full=True):
            pix = pdf.Pixmap(document, image[0])
            # MuPDF deletes the original colored pixels to white and paints
            # a black redaction rectangle separately. The blue source must be gone.
            assert pix.pixel(round(pix.width * .25), round(pix.height * .25))[:3] == (255, 255, 255)


@pytest.mark.parametrize('cancel', [False, True])
def test_submission_ocr_failure_or_cancel_never_publishes(tmp_path, monkeypatch, cancel):
    source, target = tmp_path / 'source.pdf', tmp_path / 'result.pdf'
    scan_fixture(source)
    original = source.read_bytes()
    def failure(page, cancelled):
        raise Cancelled('cancel') if cancel else ValueError('OCR unavailable')
    monkeypatch.setattr('eoingpdf.ocr.page_layout', failure)
    with pytest.raises(Cancelled if cancel else ValueError):
        transform(source, target, 'safe_submission')
    assert not target.exists() and source.read_bytes() == original
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows OCR integration')
def test_real_windows_ocr_submission(tmp_path):
    from eoingpdf.ocr import page_layout
    root = Path(__file__).resolve().parents[1]
    source, target = tmp_path / 'scan.pdf', tmp_path / 'redacted.pdf'
    image = Image.new('RGB', (1200, 600), 'white')
    font = ImageFont.truetype(str(root / 'assets/fonts/Pretendard-Regular.ttf'), 72)
    ImageDraw.Draw(image).text((90, 170), '010-1234-5678', font=font, fill='black')
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    with pdf.open() as document:
        page = document.new_page(width=400, height=200)
        page.insert_image(page.rect, stream=stream.getvalue())
        document.save(source)
    original = source.read_bytes()
    with pdf.open(source) as document:
        before = page_layout(document[0])
        assert '1234' in ''.join(line['text'] for line in before['lines'])
    assert transform(source, target, 'safe_submission') >= 1
    with pdf.open(target) as document:
        after = page_layout(document[0])
        assert '1234' not in ''.join(line['text'] for line in after['lines'])
    assert source.read_bytes() == original


def test_document_diagnostic_routes_to_combined_tool(tmp_path, monkeypatch):
    from eoingpdf.sniffer import inspect_pdf
    from eoingpdf.viewer import PdfViewer
    from eoingpdf.advanced_ui import AdvancedDialog
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / 'identity.pdf'
    with pdf.open() as document:
        page = document.new_page(width=300, height=180)
        page.insert_font(fontname='Korean', fontfile=str(root / 'assets/fonts/Pretendard-Regular.ttf'))
        page.insert_text((20, 40), '주민등록 증빙', fontname='Korean')
        document.save(source)
    report = inspect_pdf(source, budget_ms=100)
    assert next(item for item in report['diagnostics'] if item['code'] == 'D-01')['action'] == 'safe_submission'
    viewer = PdfViewer(source)
    selected = []
    monkeypatch.setattr(AdvancedDialog, 'exec', lambda dialog: selected.append((dialog.tool.currentData(), dialog.source.text())))
    try:
        viewer.diagnostic_action('safe_submission')
        assert selected == [('safe_submission', str(source))]
    finally:
        viewer.close()
