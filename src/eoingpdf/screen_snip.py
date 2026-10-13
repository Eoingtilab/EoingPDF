"""User-invoked region capture; screenshots stay in memory and no URI is registered."""
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid
from .localization import tr


class SnipOverlay(QWidget):
    picked = Signal(QImage)
    cancelled = Signal()

    def __init__(self, picture, geometry, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.picture = picture
        self.origin = None
        self.selection = QRectF()
        self.setGeometry(geometry)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.picture)
        mask = QPainterPath()
        mask.setFillRule(Qt.OddEvenFill)
        mask.addRect(QRectF(self.rect()))
        if not self.selection.isEmpty():
            mask.addRect(self.selection)
        painter.fillPath(mask, QColor(0, 0, 0, 110))
        painter.setPen(QPen(QColor('#4aa8ff'), 2))
        painter.drawRect(self.selection)
        painter.setPen(QColor('white'))
        painter.drawText(20, 34, tr('캡처할 영역을 끌어서 선택하세요 · Esc 취소'))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.position()
            self.selection = QRectF(self.origin, self.origin)

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.selection = QRectF(self.origin, event.position()).normalized().intersected(QRectF(self.rect()))
            self.update()

    def mouseReleaseEvent(self, event):
        if self.origin is not None and event.button() == Qt.LeftButton:
            self.mouseMoveEvent(event)
            area = self.selection
            self.origin = None
            if area.width() >= 5 and area.height() >= 5:
                sx, sy = self.picture.width() / self.width(), self.picture.height() / self.height()
                self.picked.emit(self.picture.copy(round(area.x() * sx), round(area.y() * sy),
                                                   round(area.width() * sx), round(area.height() * sy)).toImage())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.cancelled.emit()
        event.accept()


class ScreenSnipper(QObject):
    captured = Signal(QImage)

    def __init__(self, parent):
        super().__init__(parent)
        self.active = False
        self.hidden = []
        self.overlays = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.cancel)

    def start(self):
        if self.active:
            return
        self.active = True
        self.hidden = [(widget, widget.windowState()) for widget in QApplication.topLevelWidgets() if widget.isVisible()]
        for widget, _ in self.hidden:
            widget.hide()
        self.timer.start(45000)
        QTimer.singleShot(200, self.show_overlays)

    def show_overlays(self):
        if not self.active:
            return
        try:
            for screen in QGuiApplication.screens():
                picture = screen.grabWindow(0)
                if picture.isNull():
                    continue
                overlay = SnipOverlay(picture, screen.geometry(), self.parent().window())
                overlay.picked.connect(self.finish)
                overlay.cancelled.connect(self.cancel)
                self.overlays.append(overlay)
                overlay.show()
                overlay.raise_()
                overlay.activateWindow()
                overlay.setFocus()
            if not self.overlays:
                self.cancel()
        except Exception:
            self.cancel()

    def finish(self, image=None, restore=True):
        if not self.active:
            return
        self.active = False
        self.timer.stop()
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()
        if restore:
            for widget, state in self.hidden:
                if isValid(widget):
                    widget.setWindowState(state)
                    widget.show()
        self.hidden.clear()
        if image is not None:
            self.captured.emit(image)

    def cancel(self, *, restore=True):
        self.finish(restore=restore)
