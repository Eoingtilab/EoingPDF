from pathlib import Path
import io
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
from PIL import Image
from eoingpdf.advanced import transform

def test_empty_stamp_page_range_means_all(tmp_path):
    image = tmp_path / 'mark.png'
    Image.new('RGB', (20, 20), 'red').save(image)
    source, target = tmp_path / 'source.pdf', tmp_path / 'target.pdf'
    with pdf.open() as doc:
        for _ in range(3): doc.new_page(width=300, height=300)
        doc.save(source)
    transform(source, target, 'stamp', watermark_image=str(image), stamp_pages='', stamp_x_mm=1, stamp_y_mm=1, stamp_width_mm=10, stamp_flatten=False)
    with pdf.open(target) as doc:
        assert all(page.get_images() for page in doc)
