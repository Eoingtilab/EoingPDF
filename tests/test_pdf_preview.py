"""Real child results are reviewed in the open viewer before publication."""
import sys
from pathlib import Path
import pymupdf as pdf
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.viewer import PdfViewer
from eoingpdf.advanced_ui import AdvancedDialog
from eoingpdf.form_ui import FormDialog
from eoingpdf.stamp_editor import StampEditor


def wait(worker):
    import time
    deadline = time.monotonic() + 15
    while worker.isRunning() and time.monotonic() < deadline:
        QTest.qWait(30)
    assert worker.done
    QTest.qWait(50)


def source_pdf(path, fields=False):
    with pdf.open() as document:
        for index in range(2):
            page = document.new_page(width=400, height=500)
            page.insert_text((40, 240), f'ORIGINAL {index + 1}')
            if fields:
                field = pdf.Widget()
                field.field_name = f'name{index}'
                field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
                field.rect = pdf.Rect(30, 300, 200, 335)
                page.add_widget(field)
        document.save(path)


def no_save_dialog(*_):
    raise AssertionError('Preview must not request an output file')


def test_stamp_then_tool_preview_then_final_save(tmp_path, monkeypatch):
    source, output, seal = tmp_path / 'source.pdf', tmp_path / 'saved.pdf', tmp_path / 'seal.jpg'
    source_pdf(source)
    original = source.read_bytes()
    image = Image.new('RGB', (100, 100), 'white')
    ImageDraw.Draw(image).ellipse((10, 10, 90, 90), outline='red', width=8)
    image.save(seal)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    monkeypatch.setattr('eoingpdf.advanced_ui.QFileDialog.getSaveFileName', no_save_dialog)
    viewer = PdfViewer(source)
    viewer.page.setValue(2)
    viewer.stamp_editor = StampEditor(viewer)
    viewer.stamp_editor.add_image(seal)
    viewer.stage_current_preview()
    assert source.read_bytes() == original and viewer.dirty
    dialog = AdvancedDialog(viewer)
    dialog.source.setText(str(viewer.path))
    dialog.tool.setCurrentIndex(dialog.tool.findData('watermark_text'))
    dialog.watermark_text.setText('REVIEW BEFORE SAVE')
    dialog.start(preview=True)
    wait(dialog.worker)
    assert viewer.dirty and len(viewer.preview_owners) == 2 and viewer.page.value() == 2
    assert viewer.original_path == source and not output.exists()
    owners = [Path(owner.name) for owner in viewer.preview_owners]
    with pdf.open(viewer.path) as document:
        assert 'REVIEW BEFORE SAVE' in ' '.join(document[1].get_text().split())
        assert document[1].get_images()
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(output), 'PDF'))
    assert viewer.save_changes()
    assert all(not folder.exists() for folder in owners)
    assert not viewer.preview_owners and not viewer.dirty
    assert source.read_bytes() == original
    with pdf.open(output) as document:
        assert document[1].get_images() and 'REVIEW BEFORE SAVE' in ' '.join(document[1].get_text().split())
    viewer.close()


def test_form_preview_without_publishing_and_discard(tmp_path, monkeypatch):
    source = tmp_path / 'forms.pdf'
    source_pdf(source, fields=True)
    original = source.read_bytes()
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    monkeypatch.setattr('eoingpdf.form_ui.QFileDialog.getSaveFileName', no_save_dialog)
    viewer = PdfViewer(source)
    form = FormDialog(source, 0, viewer)
    next(iter(form.fields.values())).setText('홍길동')
    form.start()
    wait(form.worker)
    assert viewer.dirty and viewer.preview_owners
    with pdf.open(viewer.path) as document:
        assert list(document[0].widgets())[0].field_value == '홍길동'
    preview = viewer.path
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Discard)
    viewer.close()
    assert not preview.exists() and source.read_bytes() == original


def test_failed_preview_does_not_replace_open_document(tmp_path, monkeypatch):
    source = tmp_path / 'source.pdf'
    source_pdf(source)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    viewer = PdfViewer(source)
    dialog = AdvancedDialog(viewer)
    dialog.source.setText(str(source))
    dialog.tool.setCurrentIndex(dialog.tool.findData('replace_image'))
    dialog.start(preview=True)
    assert viewer.path == source and not viewer.preview_owners and not viewer.dirty
    dialog.close()
    viewer.close()


def test_slideshow_uses_draft_and_saved_ink_returns_to_same_viewer(tmp_path, monkeypatch):
    from PySide6.QtCore import QPointF
    from eoingpdf.ink_stroke import InkStroke
    source, seal, output = tmp_path / 'source.pdf', tmp_path / 'seal.jpg', tmp_path / 'ink.pdf'
    source_pdf(source)
    original = source.read_bytes()
    image = Image.new('RGB', (40, 40), 'white')
    ImageDraw.Draw(image).rectangle((4, 4, 35, 35), outline='red', width=3)
    image.save(seal)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    defaults = []
    def destination(*arguments):
        defaults.append(arguments[2])
        return str(output), 'PDF'
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', destination)
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.information', lambda *_: None)
    viewer = PdfViewer(source)
    viewer.stamp_editor = StampEditor(viewer)
    viewer.stamp_editor.add_image(seal)
    viewer.start_slideshow()
    slides = viewer.slideshow
    with pdf.open(slides.path) as document:
        assert document[0].get_images()
    slides.canvas.ink_strokes.append(InkStroke([QPointF(.1, .7), QPointF(.8, .7)]))
    assert slides.bake_annotations()
    assert Path(defaults[0]).parent == tmp_path
    slides.reject()
    assert viewer.path == output and not viewer.preview_owners
    with pdf.open(viewer.path) as document:
        assert document[0].get_images() and list(document[0].annots())
    assert source.read_bytes() == original
    viewer.close()


def test_form_preview_final_save_keeps_canonical_field_values(tmp_path, monkeypatch):
    from pypdf import PdfReader
    source, target = tmp_path / 'forms.pdf', tmp_path / 'saved.pdf'
    source_pdf(source, fields=True)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    viewer = PdfViewer(source)
    dialog = FormDialog(source, 0, viewer)
    next(iter(dialog.fields.values())).setText('홍길동')
    dialog.start()
    wait(dialog.worker)
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(target), 'PDF'))
    assert viewer.save_changes()
    fields = PdfReader(target).get_fields()
    assert fields['name0']['/V'] == '홍길동'
    with pdf.open(target) as document:
        widget = list(document[0].widgets())[0]
        assert widget.field_value == '홍길동'
        assert document.xref_get_key(widget.xref, 'AP/N')[0] == 'xref'
    viewer.close()
