"""Draft placement stays on the open page and is committed only by viewer Save."""
import io
import sys
from pathlib import Path
import pymupdf as pdf
import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.viewer import PdfViewer
from eoingpdf.stamp_editor import StampEditor, UNIT
from eoingpdf.stamping import prepare_image


def fixtures(folder, rotation=0):
    source, image = folder / 'source.pdf', folder / 'seal.jpg'
    with pdf.open() as document:
        for text in ('FIRST', 'SECOND'):
            page = document.new_page(width=400, height=500)
            page.draw_rect(page.rect, fill=(.7, .8, .9))
            page.insert_text((40, 260), text)
            page.set_rotation(rotation)
        document.save(source)
    stamp = Image.new('RGB', (120, 120), 'white')
    draw = ImageDraw.Draw(stamp)
    draw.rectangle((10, 10, 109, 109), outline=(190, 0, 0), width=8)
    stamp.save(image, quality=98)
    return source, image


@pytest.mark.parametrize('rotation', (0, 90, 180, 270))
def test_draft_drag_resize_save_and_current_page(tmp_path, monkeypatch, rotation):
    source, image = fixtures(tmp_path, rotation)
    original, original_image = source.read_bytes(), image.read_bytes()
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    viewer = PdfViewer(source)
    viewer.show()
    QTest.qWait(70)
    viewer.page.setValue(2)
    viewer.stamp_editor = editor = StampEditor(viewer)
    editor.add_image(image)
    overlay = editor.overlay
    rect = overlay.screen_rect(editor.selected)
    start = rect.center()
    end = start + QPointF(80, 90)
    for event, pos, button, buttons in ((QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton),
                                      (QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton),
                                      (QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)):
        from PySide6.QtWidgets import QApplication
        QApplication.sendEvent(overlay, QMouseEvent(event, pos, pos, button, buttons, Qt.NoModifier))
    assert editor.selected.x > 10 * UNIT and editor.selected.y > 10 * UNIT
    before_width = editor.selected.width
    editor.width.setValue(before_width / UNIT + 5)
    assert editor.selected.width > before_width
    viewer.zoom.setCurrentIndex(2)
    assert overlay.screen_rect(editor.selected).width() > 0
    assert source.read_bytes() == original and image.read_bytes() == original_image
    assert not list(tmp_path.glob('*_편집.pdf'))
    output = tmp_path / 'saved.pdf'
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(output), 'PDF'))
    assert viewer.save_changes()
    assert viewer.path == output and viewer.page.value() == 2 and not viewer.dirty
    assert not editor.stamps and not editor.panel.isVisible()
    with pdf.open(output) as document:
        assert len(document) == 2 and 'SECOND' in document[1].get_text()
        assert not document[0].get_images() and document[1].get_images()
        page = document[1]
        assert page.rotation == rotation
        raster = page.get_pixmap()
        assert any(raster.pixel(x, y)[0] > 150 and raster.pixel(x, y)[1] < 100
                   for x in range(20, raster.width, 5) for y in range(20, raster.height, 5))
    assert source.read_bytes() == original
    viewer.close()


def test_toolbar_and_reorder_keep_stamps_on_their_page(tmp_path, monkeypatch):
    source, image = fixtures(tmp_path)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    monkeypatch.setattr('eoingpdf.stamp_editor.QFileDialog.getOpenFileName', lambda *_: (str(image), 'JPEG'))
    viewer = PdfViewer(source)
    viewer.show()
    QTest.qWait(50)
    assert viewer.stamp_button.geometry().right() < viewer.more_features_button.geometry().left()
    QTest.mouseClick(viewer.stamp_button, Qt.LeftButton)
    assert viewer.stamp_editor.stamps and viewer.dirty
    viewer.move_current_page(1)
    output = tmp_path / 'reordered.pdf'
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(output), 'PDF'))
    assert viewer.save_changes()
    with pdf.open(output) as document:
        assert 'SECOND' in document[0].get_text() and not document[0].get_images()
        assert 'FIRST' in document[1].get_text() and document[1].get_images()
    viewer.close()


def test_jpeg_knockout_and_cancel_draft(tmp_path, monkeypatch):
    source, image = fixtures(tmp_path)
    stream, _ = prepare_image(image)
    with Image.open(io.BytesIO(stream)) as transparent:
        assert transparent.mode == 'RGBA'
        assert transparent.getchannel('A').getextrema() == (0, 255)
    viewer = PdfViewer(source)
    viewer.stamp_editor = editor = StampEditor(viewer)
    editor.add_image(image)
    editor.remove_selected()
    assert not viewer.dirty and not editor.stamps and not viewer.save_button.isEnabled()
    viewer.close()


def test_insert_is_visible_after_scroll_and_drag_scroll_stops(tmp_path, monkeypatch):
    source, image = fixtures(tmp_path)
    viewer = PdfViewer(source)
    viewer.show()
    QTest.qWait(60)
    bar = viewer.scroll.verticalScrollBar()
    bar.setValue(min(100, bar.maximum() // 2))
    viewer.stamp_editor = editor = StampEditor(viewer)
    editor.add_image(image)
    overlay = editor.overlay
    center = overlay.screen_rect(editor.selected).center()
    visible = overlay.mapTo(viewer.scroll.viewport(), center.toPoint())
    assert viewer.scroll.viewport().rect().contains(visible)
    overlay.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, center, center, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    end = viewer.scroll.viewport().mapToGlobal(QPoint(viewer.scroll.viewport().width() // 2, viewer.scroll.viewport().height() - 1))
    monkeypatch.setattr('eoingpdf.stamp_editor.QCursor.pos', lambda: end)
    previous = bar.value()
    overlay.scroll_drag()
    assert bar.value() >= previous
    overlay.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, center, center, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    assert not overlay.auto_scroll.isActive()
    editor.remove_selected()
    viewer.close()
