from pathlib import Path
import sys

import pymupdf as pdf
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QFileDialog, QDialog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.capture_ui import CaptureSession, CaptureChip, CaptureDialog, save_captures, session


def picture(color, width=40, height=20):
    image = QImage(width, height, QImage.Format_RGBA8888)
    image.fill(QColor(color))
    return image


def test_bounded_image_collection_and_consecutive_duplicates():
    store = CaptureSession(QApplication.instance())
    store.MAX_IMAGES = 2
    assert store.add_image(picture('red'))
    assert not store.add_image(picture('red'))
    assert store.add_image(picture('green'))
    assert store.add_image(picture('blue'))
    assert len(store.images) == 2
    assert store.images[0].pixelColor(0, 0) == QColor('green')
    store.MAX_BYTES = 40 * 20 * 4
    assert store.add_image(picture('white'))
    assert len(store.images) == 1 and store.bytes_used == store.MAX_BYTES
    assert not store.add_image(picture('black', 41, 20))
    assert not store.add_image(QImage())
    store.clear()
    assert store.bytes_used == 0 and not store.images


def test_window_scoped_shared_clipboard_subscription():
    app = QApplication.instance()
    store = session()
    assert store.listeners == 0
    windows = []
    try:
        for _ in range(2):
            window = QWidget()
            layout = QVBoxLayout(window)
            chip = CaptureChip(window)
            layout.addWidget(chip)
            windows.append((window, chip))
            window.show()
        app.processEvents()
        assert store.listeners == 2
        app.clipboard().setImage(picture('red'))
        app.clipboard().setImage(picture('blue'))
        app.processEvents()
        assert len(store.images) == 2
        assert all(chip.isVisible() for _, chip in windows)
        windows[0][0].close()
        assert store.listeners == 1 and len(store.images) == 2
        windows[1][0].deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        assert store.listeners == 0 and not store.images
        app.clipboard().setImage(picture('green'))
        assert not store.images
    finally:
        from shiboken6 import isValid
        for window, _ in windows:
            if isValid(window):
                window.close()
        app.clipboard().clear()


def test_capture_review_reorder_remove_save_and_no_overwrite(tmp_path, monkeypatch):
    target = tmp_path / 'captures.pdf'
    dialog = CaptureDialog([picture('red'), picture('green'), picture('blue')])
    try:
        dialog.files.setCurrentRow(1)
        dialog.remove_selected()
        item = dialog.files.takeItem(1)
        dialog.files.insertItem(0, item)
        monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(target), ''))
        dialog.save()
        assert dialog.result() == QDialog.DialogCode.Accepted
        with pdf.open(target) as document:
            assert len(document) == 2
            assert document[0].rect == pdf.Rect(0, 0, 30, 15)
            assert document[0].get_pixmap().pixel(10, 10) == (0, 0, 255)
            assert document[1].get_pixmap().pixel(10, 10) == (255, 0, 0)
        original = target.read_bytes()
        with pytest.raises(FileExistsError):
            save_captures([picture('green')], target)
        assert target.read_bytes() == original
        with pytest.raises(ValueError):
            save_captures([QImage()], tmp_path / 'invalid.pdf')
        assert list(tmp_path.iterdir()) == [target]
    finally:
        dialog.close()


def test_clear_capture_review_releases_shared_images():
    store = CaptureSession(QApplication.instance())
    store.add_image(picture('red'))
    dialog = CaptureDialog(list(store.images))
    dialog.discarded.connect(store.clear)
    try:
        dialog.clear_captures()
        assert not store.images and store.bytes_used == 0
        assert dialog.files.count() == 0 and not dialog.save_button.isEnabled()
    finally:
        dialog.close()
