import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree
import pymupdf as pdf
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_svg_outlines_crop_and_visible_annotations(tmp_path, rotation):
    source, target = tmp_path / 'source.pdf', tmp_path / 'pages.zip'
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.draw_rect(page.rect, fill=(1, 0, 0), color=None)
        page.draw_rect(pdf.Rect(80, 100, 520, 700), fill=(1, 1, 1), color=None)
        page.insert_text((180, 300), 'Outlined text', fontsize=24)
        note = page.add_rect_annot(pdf.Rect(150, 400, 300, 500))
        note.set_colors(stroke=(0, 0, 1), fill=(0, 0, 1))
        note.update()
        page.set_cropbox(pdf.Rect(100, 120, 500, 680))
        page.set_rotation(rotation)
        document.save(source)
    original = source.read_bytes()
    transform(source, target, 'svg')
    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == ['page-00001.svg']
        assert archive.testzip() is None
        content = archive.read('page-00001.svg')
    root = ElementTree.fromstring(content)
    assert not root.findall('.//{http://www.w3.org/2000/svg}text')
    assert root.findall('.//{http://www.w3.org/2000/svg}path')
    with pdf.open(source) as before, pdf.open(stream=content, filetype='svg') as after:
        expected = before[0].get_pixmap(colorspace=pdf.csRGB)
        actual = after[0].get_pixmap(colorspace=pdf.csRGB)
        assert (actual.width, actual.height) == (expected.width, expected.height)
        difference = np.abs(np.frombuffer(actual.samples, dtype=np.uint8).astype(int) -
                            np.frombuffer(expected.samples, dtype=np.uint8).astype(int))
        assert difference.mean() < 1
    assert source.read_bytes() == original


def test_cancel_and_existing_archive(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'pages.zip'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    with pytest.raises(Cancelled):
        transform(source, target, 'svg', cancelled=lambda: True)
    assert not target.exists() and not list(tmp_path.glob('.eoing-*'))
    target.write_bytes(b'existing')
    with pytest.raises(ValueError):
        transform(source, target, 'svg')
    assert target.read_bytes() == b'existing'


def test_images_embedded_and_safe_page_names(tmp_path):
    import io
    from PIL import Image
    stream = io.BytesIO()
    Image.new('RGB', (12, 8), (10, 80, 190)).save(stream, format='PNG')
    source, target = tmp_path / '한글 문서.pdf', tmp_path / 'images.zip'
    with pdf.open() as document:
        for _ in range(2):
            page = document.new_page(width=100, height=100)
            page.insert_image(pdf.Rect(10, 10, 90, 90), stream=stream.getvalue())
        document.save(source)
    transform(source, target, 'svg')
    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == ['page-00001.svg', 'page-00002.svg']
        for name in archive.namelist():
            root = ElementTree.fromstring(archive.read(name))
            images = root.findall('.//{http://www.w3.org/2000/svg}image')
            assert images
            for image in images:
                href = image.get('{http://www.w3.org/1999/xlink}href') or image.get('href')
                assert href.startswith('data:image/')
