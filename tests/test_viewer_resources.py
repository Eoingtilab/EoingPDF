"""Bound reader thumbnail resources without changing pages or draft history."""
from pathlib import Path
import sys

import pymupdf as pdf
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import QApplication, QAbstractItemView, QPushButton, QMessageBox, QWidget
from PySide6.QtTest import QTest
import pytest
from shiboken6 import isValid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.core import open_pdf
from eoingpdf.viewer import PdfViewer, THUMBNAIL_CARD_LIMIT


@pytest.fixture
def reader_permissions(monkeypatch):
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *_args, **_kwargs: None)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Discard)


def sample(path, count=80, *, color=0):
    with pdf.open() as document:
        for index in range(count):
            page = document.new_page(width=300, height=420)
            page.draw_rect(page.rect, fill=((index + color) % 9 / 10, .3, .6), color=None)
            page.insert_text((30, 60), f'PAGE {index + 1}')
            if index % 7 == 0:
                page.set_rotation(90)
        document.save(path)


def flush():
    QApplication.instance().processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def fill_at(viewer, row):
    viewer.thumbnails.scrollToItem(viewer.thumbnails.item(row), QAbstractItemView.PositionAtTop)
    for _ in range(3):
        viewer.fill_thumbnails()
    flush()
    viewer.fit_timer.stop()
    viewer.thumbnail_timer.stop()


def assert_thumbnail_matches_source(viewer, row):
    card = viewer.thumbnails.itemWidget(viewer.thumbnails.item(row))
    assert card is not None
    actual = card.findChild(QPushButton, 'thumbnailPage').icon().pixmap(112, 144).toImage()
    with open_pdf(viewer.path, viewer.password) as document:
        page = document[viewer.pages[row]]
        scale = min(112 / page.rect.width, 144 / page.rect.height)
        raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
        image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
        expected = QIcon(QPixmap.fromImage(image)).pixmap(112, 144).toImage()
    assert actual.size() == expected.size()
    assert actual == expected
    return card


def test_visited_thumbnail_cards_are_bounded_and_can_be_recreated(tmp_path, reader_permissions):
    source = tmp_path / 'many-pages.pdf'
    sample(source)
    original = source.read_bytes()
    viewer = PdfViewer(source)
    try:
        viewer.show()
        flush()
        fill_at(viewer, 0)
        first = assert_thumbnail_matches_source(viewer, 0)
        for row in range(0, viewer.count, 4):
            fill_at(viewer, row)
            assert len(viewer.thumbnail_cache) <= THUMBNAIL_CARD_LIMIT
            assert sum(viewer.thumbnails.itemWidget(viewer.thumbnails.item(index)) is not None
                       for index in range(viewer.count)) <= THUMBNAIL_CARD_LIMIT
        assert not isValid(first)  # Removed Qt widgets / pixmaps are actually released.
        fill_at(viewer, 0)
        recreated = assert_thumbnail_matches_source(viewer, 0)
        assert recreated is not first
        viewer.page.setValue(4)
        recreated.findChild(QPushButton, 'thumbnailPage').click()
        assert viewer.page.value() == 1 and not viewer.dirty
        assert source.read_bytes() == original
    finally:
        viewer.close()
        flush()


def test_thumbnail_eviction_retains_page_order_history_zoom_and_new_document(tmp_path, reader_permissions):
    source, other = tmp_path / 'original.pdf', tmp_path / 'other.pdf'
    sample(source)
    sample(other, color=4)
    original = source.read_bytes()
    viewer = PdfViewer(source)
    try:
        viewer.show()
        flush()
        for row in range(0, viewer.count, 4):
            fill_at(viewer, row)
        viewer.page.setValue(1)
        viewer.move_current_page(1)
        fill_at(viewer, 0)
        assert viewer.pages[:2] == [1, 0]
        assert_thumbnail_matches_source(viewer, 0)
        viewer.zoom.setCurrentText('150%')
        assert viewer.canvas.width() == 630  # Source page zero has 90 degree rotation.
        assert viewer.undo_edit() and viewer.pages[:2] == [0, 1]
        fill_at(viewer, 0)
        assert_thumbnail_matches_source(viewer, 0)
        assert viewer.redo_edit() and viewer.pages[:2] == [1, 0]
        fill_at(viewer, 0)
        assert_thumbnail_matches_source(viewer, 0)
        viewer.load(other)
        fill_at(viewer, 0)
        assert_thumbnail_matches_source(viewer, 0)
        assert viewer.pages == list(range(80)) and not viewer.dirty
        assert source.read_bytes() == original
    finally:
        viewer.close()
        flush()


def test_populated_thumbnail_window_does_not_reopen_pdf(tmp_path, reader_permissions, monkeypatch):
    source = tmp_path / 'small.pdf'
    sample(source, 4)
    viewer = PdfViewer(source)
    try:
        viewer.show()
        flush()
        fill_at(viewer, 0)
        assert len(viewer.thumbnail_cache) == 4

        calls = []

        def unexpected_open(*_args, **_kwargs):
            calls.append(True)
            raise AssertionError('No unrendered thumbnail needs a document open')

        monkeypatch.setattr('eoingpdf.viewer.open_pdf', unexpected_open)
        viewer.fill_thumbnails()
        assert len(viewer.thumbnail_cache) == 4
        assert not calls
    finally:
        viewer.close()
        flush()


def test_closed_parented_reader_releases_rasters_and_pending_resize_timer(tmp_path, reader_permissions):
    source = tmp_path / 'parented.pdf'
    sample(source, 4)
    parent = QWidget()
    viewer = PdfViewer(source, parent)
    try:
        viewer.show()
        flush()
        fill_at(viewer, 0)
        assert viewer.thumbnail_cache and not viewer.canvas.pixmap().isNull()
        viewer.fit_timer.start(20)
        viewer.close()
        flush()
        assert isValid(viewer) and viewer.parent() is parent
        assert not viewer.fit_timer.isActive() and not viewer.thumbnail_timer.isActive()
        assert not viewer.thumbnail_cache and viewer.thumbnails.count() == 0
        assert viewer.canvas.pixmap().isNull()
        QTest.qWait(40)
        assert viewer.canvas.pixmap().isNull() and viewer.thumbnails.count() == 0
    finally:
        viewer.close()
        parent.close()
        parent.deleteLater()
        flush()
