import sys
from pathlib import Path
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.screen_snip import SnipOverlay, ScreenSnipper


def test_selected_region_maps_to_physical_pixels_without_overlays():
    picture = QPixmap(800, 600)
    picture.fill(Qt.red)
    overlay = SnipOverlay(picture, QRect(0, 0, 400, 300))
    results = []
    overlay.picked.connect(results.append)
    overlay.show()
    QTest.mousePress(overlay, Qt.LeftButton, pos=QPoint(50, 60))
    QTest.mouseMove(overlay, QPoint(250, 210))
    QTest.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(250, 210))
    assert results and (results[0].width(), results[0].height()) == (400, 300)
    assert results[0].pixelColor(10, 10) == Qt.red
    overlay.close()


def test_cancel_restores_windows_before_any_screen_is_read():
    owner = QWidget()
    owner.show()
    snipper = ScreenSnipper(owner)
    snipper.start()
    assert snipper.active and not owner.isVisible()
    snipper.cancel()
    assert owner.isVisible() and not snipper.active and not snipper.timer.isActive()
    assert not snipper.overlays and not snipper.hidden
    owner.close()
