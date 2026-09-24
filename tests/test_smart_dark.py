import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
from PIL import Image
from eoingpdf.advanced import transform

def test_smart_dark_preserves_photo_and_inverts_page(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'dark.pdf'
    image = io.BytesIO(); Image.new('RGB', (40, 40), (20, 120, 220)).save(image, format='PNG')
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=240)
        page.insert_text((30, 50), 'Dark text')
        page.insert_image(pdf.Rect(120, 80, 200, 160), stream=image.getvalue())
        doc.save(source)
    transform(source, target, 'smart_dark')
    with pdf.open(target) as doc:
        page = doc[0]
        assert not page.get_text().strip()
        raster = page.get_pixmap()
        # white background is now black, while the blue photo remains blue.
        assert raster.pixel(10, 10) == (0, 0, 0)
        blue = raster.pixel(160, 120)
        assert blue[2] > 150 and blue[0] < 80

def test_smart_dark_rotated_source_preserves_rotation(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'dark.pdf'
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=240)
        page.insert_text((30, 50), 'rotated')
        page.set_rotation(90)
        doc.save(source)
    transform(source, target, 'smart_dark')
    with pdf.open(target) as doc:
        assert doc[0].rotation == 0
        assert doc[0].rect.width == 240 and doc[0].rect.height == 300
