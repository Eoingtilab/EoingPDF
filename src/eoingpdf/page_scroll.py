"""Wheel navigation at PDF page boundaries, with normal in-page scrolling."""
from time import monotonic
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QScrollArea


class PageScrollArea(QScrollArea):
    page_requested = Signal(int)
    interacted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edge_delta = 0
        self._last_wheel = 0.0
        self._last_turn = 0.0

    def wheelEvent(self, event):
        self.interacted.emit()
        if event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier):
            self._edge_delta = 0
            return super().wheelEvent(event)
        pixel = event.pixelDelta()
        angle = event.angleDelta()
        delta = pixel.y() if not pixel.isNull() else angle.y()
        horizontal = pixel.x() if not pixel.isNull() else angle.x()
        if not delta or abs(horizontal) > abs(delta):
            self._edge_delta = 0
            return super().wheelEvent(event)
        bar = self.verticalScrollBar()
        at_edge = bar.value() >= bar.maximum() if delta < 0 else bar.value() <= bar.minimum()
        now = monotonic()
        if not at_edge:
            self._edge_delta = 0
            self._last_wheel = now
            return super().wheelEvent(event)
        if event.phase() == Qt.ScrollMomentum:
            event.accept()
            return
        if now - self._last_wheel > .3 or self._edge_delta * delta < 0:
            self._edge_delta = 0
        self._last_wheel = now
        # Touchpad pixels and high-resolution wheel deltas accumulate separately.
        unit = 'pixel' if not pixel.isNull() else 'angle'
        if unit != getattr(self, '_unit', unit):
            self._edge_delta = 0
        self._unit = unit
        self._edge_delta += delta
        threshold = 48 if unit == 'pixel' else 120
        if abs(self._edge_delta) >= threshold and now - self._last_turn >= .18:
            self._edge_delta = 0
            self._last_turn = now
            self.page_requested.emit(1 if delta < 0 else -1)
        event.accept()
