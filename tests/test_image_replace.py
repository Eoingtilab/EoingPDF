import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pytest
import pymupdf as pdf
from PIL import Image
from eoingpdf.advanced import transform
from eoingpdf.image_replace import inventory
from eoingpdf.core import Cancelled


def test_original_image_picker_is_available_before_selection(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QFileDialog
    from eoingpdf.advanced_ui import AdvancedDialog
    dialog = AdvancedDialog()
    opened = []
    class Choice:
        selected = (7, 'verified-digest')
        def __init__(self, path, password, parent):
            opened.append(path)
        def exec(self):
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr('eoingpdf.image_choice_ui.ImageChoiceDialog', Choice)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: pytest.fail('Must choose original image first'))
    try:
        dialog.tool.setCurrentIndex(dialog.tool.findData('replace_image'))
        dialog.source.setText(str(tmp_path / 'source.pdf'))
        dialog.start()
        assert '먼저 원본 이미지 선택' in dialog.status.text()
        dialog.choose_original_image()
        assert opened == [str(tmp_path / 'source.pdf')]
        assert dialog.replace_selection == (7, 'verified-digest')
        dialog.source.setText(str(tmp_path / 'another.pdf'))
        assert dialog.replace_selection == (0, '')
    finally:
        dialog.close()


def png(color, size=(60, 30)):
    stream = io.BytesIO()
    Image.new('RGB', size, color).save(stream, format='PNG')
    return stream.getvalue()


@pytest.fixture
def fixture(tmp_path):
    source, replacement = tmp_path / 'source.pdf', tmp_path / 'new.png'
    replacement.write_bytes(png('blue', (30, 30)))
    with pdf.open() as doc:
        first = doc.new_page(width=300, height=240)
        xref = first.insert_image(pdf.Rect(40, 40, 160, 100), stream=png('red'))
        first.insert_image(pdf.Rect(180, 40, 240, 70), stream=png('green'))
        first.insert_text((40, 180), 'Keep this text')
        second = doc.new_page(width=300, height=240)
        second.insert_image(pdf.Rect(40, 40, 160, 100), xref=xref)
        second.set_rotation(90)
        third = doc.new_page(width=300, height=240)
        duplicate = third.insert_image(pdf.Rect(40, 40, 160, 100), stream=png('yellow'))
        doc.xref_copy(xref, duplicate)
        doc.save(source)
    return source, replacement, xref


def test_replace_shared_and_duplicate_pixel_identity(fixture, tmp_path):
    source, replacement, xref = fixture
    original = source.read_bytes()
    target = tmp_path / 'result.pdf'
    with pdf.open(source) as doc:
        entries = inventory(doc)
        digest = next(entry['digest'] for entry in entries if entry['xref'] == xref)
    transform(source, target, 'replace_image', watermark_image=str(replacement), replace_xref=xref, replace_digest=digest)
    with pdf.open(target) as doc, pdf.open(source) as before:
        for index, page in enumerate(doc):
            assert page.rotation == before[index].rotation
            page.set_rotation(0)
            raster = page.get_pixmap()
            assert raster.pixel(100, 60) == (0, 0, 255)
            assert raster.pixel(45, 60) == (255, 255, 255)  # transparent padding, no stretching
        assert 'Keep this text' in doc[0].get_text()
        assert doc[0].get_pixmap().pixel(200, 50) == (0, 128, 0)
    assert source.read_bytes() == original


@pytest.mark.parametrize('options', ({'replace_xref': 99999}, {'replace_digest': 'stale'}, {'cancelled': lambda: True}))
def test_invalid_stale_and_cancel(fixture, tmp_path, options):
    source, replacement, xref = fixture
    target = tmp_path / 'result.pdf'
    values = dict(replace_xref=xref, watermark_image=str(replacement))
    values.update(options)
    with pytest.raises((ValueError, Cancelled)):
        transform(source, target, 'replace_image', **values)
    assert not target.exists() and not list(tmp_path.glob('.eoing-*'))
