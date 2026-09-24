import sys
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.presentation_canvas import LASER_TRAIL_SECONDS, PresentationCanvas


def test_laser_trail_expires_inside_half_second_window():
    app = QApplication.instance() or QApplication([])
    canvas = PresentationCanvas()
    canvas.resize(400, 300)
    canvas.show()
    canvas.toggle_laser()
    canvas.move_pointer(QPointF(200, 150))
    assert canvas.trail and canvas.fade_timer.isActive()
    QTest.qWait(round((LASER_TRAIL_SECONDS + .12) * 1000))
    assert not canvas.trail and not canvas.fade_timer.isActive()
    canvas.close()
    app.processEvents()
