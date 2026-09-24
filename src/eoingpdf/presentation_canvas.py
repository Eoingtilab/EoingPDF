"""Presentation masks and ink stored in normalized visible-page coordinates."""
from .localization import tr
from collections import deque
from time import monotonic
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QEvent, Signal
from PySide6.QtGui import QPainter, QColor, QPainterPath, QPen, QGuiApplication
from PySide6.QtWidgets import QLabel, QLineEdit
from .ink_stroke import InkStroke

LASER_TRAIL_SECONDS = .45


class PresentationCanvas(QLabel):
    text_edit_started = Signal()
    def __init__(self):
        super().__init__()
        self.reveal_fraction = 1.0
        self.mask_suspended = False
        self.board_mode = False
        self.spotlight = False
        self.laser = False
        self.pointer = QPointF(.5, .5)
        self.trail = deque(maxlen=256)
        self.ink_enabled = False
        self.ink_width = 2.5
        self.ink_tool = 'pen'
        self.page_size = (1, 1)
        self.text_lines = []
        self._highlight_preview = []
        self.ink_strokes = []
        self._ghost_surfaces = {}
        self._ink_current = None
        self.native_ink = None
        self.text_editor = QLineEdit(self)
        self.text_editor.setMaxLength(256)
        self.text_editor.setPlaceholderText(tr('내용 입력 · Enter 적용 · Esc 취소'))
        self.text_editor.hide()
        self.text_error = QLabel(self)
        self.text_error.setWordWrap(True)
        self.text_error.setStyleSheet('QLabel {background:#fff0ef;color:#a02020;padding:4px;}')
        self.text_error.hide()
        self.text_editor.installEventFilter(self)
        self._text_preedit = False
        self._text_anchor = QPointF()
        self._text_color = (0, 0, 0)
        self.fade_timer = QTimer(self)
        self.fade_timer.setInterval(16)
        self.fade_timer.setTimerType(Qt.PreciseTimer)
        self.fade_timer.timeout.connect(self.expire_trail)
        self.ghost_timer = QTimer(self)
        self.ghost_timer.setInterval(16)
        self.ghost_timer.timeout.connect(self.expire_ghosts)
        self.setMouseTracking(True)

    def toggle_spotlight(self):
        self.spotlight = not self.spotlight
        self.update()

    def toggle_laser(self):
        self.laser = not self.laser
        if not self.laser:
            self.trail.clear()
            self.fade_timer.stop()
        self.setCursor(Qt.BlankCursor if self.laser else Qt.ArrowCursor)
        self.update()

    def toggle_ink(self):
        self.ink_enabled = not self.ink_enabled
        if not self.ink_enabled:
            self._ink_current = None
        self.setCursor(Qt.CrossCursor if self.ink_enabled else Qt.ArrowCursor)
        self.update()

    def set_tool(self, tool):
        if tool not in ('pen', 'highlight', 'ghost', 'shape', 'text'):
            raise ValueError(tr('지원하지 않는 판서 도구입니다.'))
        self._ink_current = None
        self._highlight_preview = []
        self.ink_tool = tool
        self.ink_enabled = True
        self.setCursor(Qt.CrossCursor)
        self.update()

    def expire_ghosts(self):
        now = monotonic()
        if self._ink_current is not None and self._ink_current.kind == 'ghost':
            self._ink_current.created = now
        self.ink_strokes[:] = [stroke for stroke in self.ink_strokes
                              if getattr(stroke, 'kind', '') != 'ghost' or stroke.alpha(now) > 0]
        for key, strokes in list(self._ghost_surfaces.items()):
            if strokes is self.ink_strokes:
                del self._ghost_surfaces[key]
                continue
            strokes[:] = [stroke for stroke in strokes
                          if getattr(stroke, 'kind', '') != 'ghost' or stroke.alpha(now) > 0]
            if not any(getattr(stroke, 'kind', '') == 'ghost' for stroke in strokes):
                del self._ghost_surfaces[key]
        if not self._ghost_surfaces and not any(getattr(stroke, 'kind', '') == 'ghost' for stroke in self.ink_strokes):
            self.ghost_timer.stop()
        elif not self.ghost_timer.isActive():
            self.ghost_timer.start()
        self.update()

    def clear_ink(self):
        self.ink_strokes.clear()
        self._ink_current = None
        self._highlight_preview = []
        self.expire_ghosts()

    def expire_trail(self):
        # A 16ms paint tick can be delayed while a full-screen PDF is rendering.
        # End inside the promised half-second window rather than leaving a stale
        # frame visible after it.
        cutoff = monotonic() - LASER_TRAIL_SECONDS
        while self.trail and self.trail[0][0] <= cutoff:
            self.trail.popleft()
        if not self.trail:
            self.fade_timer.stop()
        self.update()

    def mouseMoveEvent(self, event):
        if self.ink_enabled and self._ink_current is not None:
            self._append_ink(event.position())
            self.update()
            event.accept()
            return
        self.move_pointer(event.position())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self.ink_enabled and event.button() == Qt.LeftButton:
            if self.ink_tool == 'text':
                self.begin_text(event.position())
                event.accept()
                return
            if not self.mask_suspended and self.page_rect().contains(event.position()):
                self._ink_current = InkStroke([self._normalized(event.position())], self.ink_tool)
                self._highlight_preview = []
                if self.ink_tool != 'highlight':
                    self.ink_strokes.append(self._ink_current)
                if self.ink_tool == 'ghost':
                    self.ghost_timer.start()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.ink_enabled and event.button() == Qt.LeftButton:
            if self._ink_current is not None:
                self._append_ink(event.position())
                if len(self._ink_current) == 1 and self._ink_current.kind != 'highlight':
                    self.ink_strokes.remove(self._ink_current)
                if self._ink_current.kind == 'ghost':
                    self._ink_current.created = monotonic()
                if self._ink_current.kind == 'shape':
                    from .shape_snap import snap_shape
                    result = snap_shape(self._ink_current, *self.page_size)
                    if result is not None:
                        self._ink_current.shape = result[0]
                        self._ink_current[:] = [QPointF(x, y) for x, y in result[1]]
            self._ink_current = None
            self._highlight_preview = []
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.begin_text(event.position())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def begin_text(self, position):
        if self.mask_suspended or not self.page_rect().contains(position):
            return
        if self.text_editor.isVisible() and not self.commit_text():
            return
        self._ink_current = None
        self.text_error.hide()
        self._text_anchor = self._normalized(position)
        image = self.pixmap().toImage()
        px = min(image.width() - 1, round(self._text_anchor.x() * (image.width() - 1)))
        py = min(image.height() - 1, round(self._text_anchor.y() * (image.height() - 1)))
        samples = [image.pixelColor(x, y) for x in range(max(0, px - 2), min(image.width(), px + 3))
                   for y in range(max(0, py - 2), min(image.height(), py + 3))]
        brightness = sum(.2126 * p.redF() + .7152 * p.greenF() + .0722 * p.blueF() for p in samples) / len(samples)
        self._text_color = (0, 0, 0) if brightness > .5 else (1, 1, 1)
        foreground = '#111111' if brightness > .5 else '#ffffff'
        background = '#ffffff' if brightness > .5 else '#111111'
        self.text_editor.setStyleSheet(f'QLineEdit {{color:{foreground};background:{background};border:1px solid #617aff;padding:4px;}}')
        self.text_editor.setGeometry(round(position.x()), round(position.y()),
                                     max(40, min(420, round(self.page_rect().right() - position.x()))), 38)
        from .ink_text import text_family
        font = self.text_editor.font()
        try:
            font.setFamily(text_family())
        except ValueError as error:
            self.show_text_error(str(error))
            return
        self.text_editor.setFont(font)
        self.text_editor.clear()
        self._text_preedit = False
        self.text_editor.show()
        self.text_editor.raise_()
        self.text_editor.setFocus()
        self.text_edit_started.emit()
        if self.native_ink is not None:
            self.native_ink.hide()
        self.update()

    def commit_text(self):
        if not self.text_editor.isVisible():
            return True
        if self._text_preedit:
            QGuiApplication.inputMethod().commit()
            if self._text_preedit:
                return False
        from .ink_text import text_strokes
        try:
            strokes = text_strokes(self.text_editor.text(), self._text_anchor, self.page_size, self._text_color)
        except ValueError as error:
            self.show_text_error(str(error))
            self.text_editor.setFocus()
            return False
        self.ink_strokes.extend(strokes)
        self.text_editor.hide()
        self.text_error.hide()
        self.text_editor.clear()
        self.window().setFocus()
        self.update()
        return True

    def show_text_error(self, message):
        self.text_error.setText(message)
        self.text_error.setFixedWidth(max(180, self.text_editor.width()))
        self.text_error.adjustSize()
        self.text_error.move(self.text_editor.x(), min(self.height() - self.text_error.height(),
                                                       self.text_editor.y() + self.text_editor.height() + 2))
        self.text_error.show()
        self.text_error.raise_()

    def eventFilter(self, watched, event):
        if watched is self.text_editor and event.type() == QEvent.InputMethod:
            self._text_preedit = bool(event.preeditString())
        if watched is self.text_editor and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._text_preedit:
                QGuiApplication.inputMethod().commit()
            else:
                self.commit_text()
            return True
        if watched is self.text_editor and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            QGuiApplication.inputMethod().reset()
            self._text_preedit = False
            self.text_editor.clear()
            self.text_editor.hide()
            self.text_error.hide()
            self.window().setFocus()
            self.update()
            return True
        return super().eventFilter(watched, event)

    def page_rect(self):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return QRectF()
        size = pixmap.deviceIndependentSize()
        return QRectF((self.width() - size.width()) / 2,
                      (self.height() - size.height()) / 2, size.width(), size.height())

    def _normalized(self, position):
        rect = self.page_rect()
        return QPointF(min(1, max(0, (position.x() - rect.left()) / max(1, rect.width()))),
                       min(1, max(0, (position.y() - rect.top()) / max(1, rect.height()))))

    def _append_ink(self, position):
        point = self._normalized(position)
        if self._ink_current.kind == 'highlight':
            old = {id(stroke) for stroke in self._highlight_preview}
            self.ink_strokes[:] = [stroke for stroke in self.ink_strokes if id(stroke) not in old]
            selected = QRectF(self._ink_current[0], point).normalized().adjusted(-.005, -.005, .005, .005)
            self._highlight_preview = [InkStroke([rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()], 'highlight')
                                       for rect in self.text_lines if rect.intersects(selected)]
            self.ink_strokes.extend(self._highlight_preview)
            return
        if self._ink_current[-1] != point:
            self._ink_current.append(point)

    def set_ink(self, strokes):
        self._ink_current = None
        if strokes is not self.ink_strokes and any(getattr(stroke, 'kind', '') == 'ghost' for stroke in self.ink_strokes):
            self._ghost_surfaces[id(self.ink_strokes)] = self.ink_strokes
        self.ink_strokes = strokes
        self._highlight_preview = []
        self.expire_ghosts()

    def move_pointer(self, position):
        self.pointer = QPointF(position.x() / max(1, self.width()),
                               position.y() / max(1, self.height()))
        if self.laser and not self.mask_suspended:
            self.trail.append((monotonic(), QPointF(self.pointer)))
            self.fade_timer.start()
        if self.laser or self.spotlight:
            self.update()

    def hideEvent(self, event):
        self.fade_timer.stop()
        self.trail.clear()
        self.ghost_timer.stop()
        if self.native_ink is not None:
            self.native_ink.close()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.expire_ghosts()

    def enable_native_ink(self):
        if self.native_ink is None and QGuiApplication.platformName() == 'windows':
            from .ink_controller import InkController
            self.native_ink = InkController(self)
        return self.native_ink

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.native_ink is not None:
            self.native_ink.request()
        pixmap = self.pixmap()
        if self.mask_suspended or pixmap is None or pixmap.isNull():
            return
        size = pixmap.deviceIndependentSize()
        top = (self.height() - size.height()) / 2
        left = (self.width() - size.width()) / 2
        cutoff = top + size.height() * self.reveal_fraction
        painter = QPainter(self)
        if self.reveal_fraction < 1 and not self.board_mode:
            painter.fillRect(int(left), int(cutoff), int(size.width()) + 1,
                             int(top + size.height() - cutoff) + 1, QColor('black'))
        painter.setRenderHint(QPainter.Antialiasing)
        if self.spotlight and not self.board_mode:
            mask = QPainterPath()
            mask.setFillRule(Qt.OddEvenFill)
            mask.addRect(QRectF(self.rect()))
            radius = min(self.width(), self.height()) * .12
            center = QPointF(self.pointer.x() * self.width(), self.pointer.y() * self.height())
            mask.addEllipse(center, radius, radius)
            painter.fillPath(mask, QColor(0, 0, 0, 185))
        if self.laser:
            now = monotonic()
            painter.setPen(Qt.NoPen)
            for timestamp, point in self.trail:
                opacity = max(0, 1 - (now - timestamp) / LASER_TRAIL_SECONDS)
                painter.setBrush(QColor(255, 35, 55, round(255 * opacity)))
                painter.drawEllipse(QPointF(point.x() * self.width(), point.y() * self.height()), 5, 5)
        if self.ink_strokes and not (self.native_ink and self.native_ink.active):
            for stroke in self.ink_strokes:
                if len(stroke) < 2:
                    continue
                opacity = stroke.alpha() if hasattr(stroke, 'alpha') else .9
                color = QColor.fromRgbF(*getattr(stroke, 'color', (1, .82, 0)), opacity)
                painter.setPen(QPen(color, self.ink_width * getattr(stroke, 'width', 2.5) / 2.5,
                                    Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                path = QPainterPath(QPointF(left + stroke[0].x() * size.width(),
                                            top + stroke[0].y() * size.height()))
                for point in stroke[1:]:
                    path.lineTo(left + point.x() * size.width(), top + point.y() * size.height())
                if getattr(stroke, 'fill', False):
                    path.closeSubpath()
                    painter.fillPath(path, color)
                else:
                    painter.drawPath(path)
        painter.end()
