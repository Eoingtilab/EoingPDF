from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
import pytest
from eoingpdf.sniffer import inspect_pdf

@pytest.mark.parametrize('pages', [1, 2])
def test_multiple_page_images_propose_stitch(tmp_path, pages):
    path = tmp_path / 'captures.pdf'
    with pdf.open() as doc:
        page = doc.new_page(width=600, height=1000)
        # Valid tiny image streams with two distinct placements.
        import io
        from PIL import Image
        data = io.BytesIO(); Image.new('RGB', (10, 10), 'red').save(data, format='PNG')
        page.insert_image(pdf.Rect(20, 20, 580, 430), stream=data.getvalue())
        page.insert_image(pdf.Rect(20, 470, 580, 900), stream=data.getvalue())
        if pages > 1:
            doc.new_page()
        doc.save(path)
    report = inspect_pdf(path, budget_ms=100)
    assert not any(item['code'] == 'D-08' for item in report['diagnostics'])
    findings = [item for item in report['diagnostics'] if item['code'] == 'CONTENT-IMAGES']
    assert bool(findings) == (pages > 1)
    if findings:
        assert findings[0]['action'] == 'stitch'
