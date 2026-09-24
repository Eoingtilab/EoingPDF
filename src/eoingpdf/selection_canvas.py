"""Viewer selection in device-independent widget coordinates."""
from PySide6.QtCore import Qt, QRect, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QLabel, QRubberBand


class SelectionCanvas(QLabel):
    selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selecting = False
        self.origin = None
        self.band = QRubberBand(QRubberBand.Rectangle, self)
        self.search_highlight = None

    def set_search_highlight(self, rect=None):
        self.search_highlight = QRectF(rect) if rect is not None else None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.search_highlight is None:
            return
        rect = self.search_highlight
        painter = QPainter(self)
        painter.setPen(QPen(QColor('#c98600'), 2))
        painter.setBrush(QColor(255, 210, 40, 75))
        painter.drawRect(QRectF(rect.x() * self.width(), rect.y() * self.height(),
                               rect.width() * self.width(), rect.height() * self.height()))

    def set_selecting(self, enabled):
        self.selecting = enabled
        self.origin = None
        self.band.hide()
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if self.selecting and event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.band.setGeometry(QRect(self.origin, self.origin))
            self.band.show()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.band.setGeometry(QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.origin is not None and event.button() == Qt.LeftButton:
            rect = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
            self.origin = None
            self.band.hide()
            if rect.width() >= 5 and rect.height() >= 5:
                self.selected.emit(rect)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
