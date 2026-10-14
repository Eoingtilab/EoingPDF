"""Draft stamps on the open PDF canvas; nothing is written until viewer Save."""
from dataclasses import dataclass
import hashlib
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QCursor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QDoubleSpinBox, QFileDialog, QDialog, QMessageBox
from .localization import tr
from .stamping import prepare_image, place_prepared
from .action_icons import set_action_icon
from .flow_layout import FlowLayout

UNIT = 72 / 25.4


@dataclass
class DraftStamp:
    page: int
    stream: bytes
    pixmap: QPixmap
    aspect: float
    x: float
    y: float
    width: float
    page_width: float
    page_height: float
    image_key: bytes = b''

    def rect(self):
        return QRectF(self.x, self.y, self.width, self.width / self.aspect)

    def fit(self):
        self.width = max(min(UNIT, self.page_width, self.page_height * self.aspect),
                         min(self.width, self.page_width, self.page_height * self.aspect))
        self.x = max(0, min(self.x, self.page_width - self.width))
        self.y = max(0, min(self.y, self.page_height - self.width / self.aspect))


class StampOverlay(QWidget):
    def __init__(self, editor):
        super().__init__(editor.viewer.canvas)
        self.editor = editor
        self.drag = None
        self.auto_scroll = QTimer(self)
        self.auto_scroll.setInterval(40)
        self.auto_scroll.timeout.connect(self.scroll_drag)
        self.setMouseTracking(True)
        self.hide()

    def scale(self):
        width, height = self.editor.viewer.visible_page_size
        return self.width() / width, self.height() / height

    def screen_rect(self, stamp):
        sx, sy = self.scale()
        return QRectF(stamp.x * sx, stamp.y * sy, stamp.width * sx, stamp.width / stamp.aspect * sy)

    def handle(self, stamp):
        point = self.screen_rect(stamp).bottomRight()
        return QRectF(point.x() - 7, point.y() - 7, 14, 14)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        for stamp in self.editor.visible_stamps():
            rect = self.screen_rect(stamp)
            painter.drawPixmap(rect, stamp.pixmap, QRectF(stamp.pixmap.rect()))
            if stamp is self.editor.selected:
                painter.setPen(QPen(QColor('#497dff'), 2, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect)
                painter.setPen(QPen(QColor('#497dff'), 1))
                painter.setBrush(QColor('white'))
                painter.drawRect(self.handle(stamp))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        position = event.position()
        stamp = self.editor.selected
        if stamp in self.editor.visible_stamps() and self.handle(stamp).contains(position):
            mode = 'resize'
        else:
            stamp = next((item for item in reversed(self.editor.visible_stamps())
                          if self.screen_rect(item).contains(position)), None)
            mode = 'move'
        self.editor.select(stamp)
        if stamp is not None:
            self.editor.begin_gesture('직인 크기 조절' if mode == 'resize' else '직인 이동')
            sx, sy = self.scale()
            self.drag = (mode, QPointF(position.x() / sx, position.y() / sy), stamp.x, stamp.y, stamp.width)
            self.auto_scroll.start()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        stamp = self.editor.selected
        if self.drag and stamp is not None:
            mode, origin, x, y, width = self.drag
            sx, sy = self.scale()
            point = QPointF(event.position().x() / sx, event.position().y() / sy)
            delta = point - origin
            if mode == 'move':
                stamp.x, stamp.y = x + delta.x(), y + delta.y()
            else:
                stamp.width = width + (delta.x() + delta.y() / stamp.aspect) / (1 + 1 / stamp.aspect ** 2)
                stamp.width = max(UNIT, min(stamp.width, stamp.page_width - x,
                                            (stamp.page_height - y) * stamp.aspect))
            stamp.fit()
            self.editor.changed(record=False)
            event.accept()
        else:
            resizing = stamp in self.editor.visible_stamps() and self.handle(stamp).contains(event.position())
            self.setCursor(Qt.SizeFDiagCursor if resizing else Qt.ArrowCursor)
            event.ignore()

    def mouseReleaseEvent(self, event):
        self.auto_scroll.stop()
        self.drag = None
        self.editor.finish_gesture()
        event.accept()

    def scroll_drag(self):
        if not self.drag or not self.isVisible():
            self.auto_scroll.stop()
            return
        scroll = self.editor.viewer.scroll
        point = scroll.viewport().mapFromGlobal(QCursor.pos())
        moved = False
        for value, extent, bar in ((point.x(), scroll.viewport().width(), scroll.horizontalScrollBar()),
                                   (point.y(), scroll.viewport().height(), scroll.verticalScrollBar())):
            delta = -24 if value < 20 else 24 if value > extent - 20 else 0
            previous = bar.value()
            bar.setValue(previous + delta)
            moved |= bar.value() != previous
        if moved:
            # Reuse the drag's document coordinates after the viewport scrolls.
            from PySide6.QtCore import QEvent
            from PySide6.QtGui import QMouseEvent
            position = QPointF(self.mapFromGlobal(QCursor.pos()))
            self.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, position, position, Qt.NoButton, Qt.LeftButton, Qt.NoModifier))

    def hideEvent(self, event):
        self.auto_scroll.stop()
        self.drag = None
        self.editor.finish_gesture()
        super().hideEvent(event)


class StampEditor:
    def __init__(self, viewer):
        self.viewer = viewer
        self.stamps = []
        self.selected = None
        self.image_cache = {}
        self.image_bytes = 0
        self.gesture_label = None
        self.overlay = StampOverlay(self)
        self.panel = QWidget(viewer)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.hint = QLabel(tr('끌어서 이동 · 오른쪽 아래 모서리로 크기 조절 · 마지막에 저장'))
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        controls = QWidget(self.panel)
        row = FlowLayout(controls)
        row.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(controls)
        for label, callback, icon in ((tr('이미지 추가'), self.choose_image, 'image'),
                                      (tr('도장 보관함'), self.choose_vault, 'vault')):
            button = QPushButton(label)
            set_action_icon(button, icon)
            button.clicked.connect(callback)
            row.addWidget(button)
        width_group = QWidget(controls)
        width_row = QHBoxLayout(width_group)
        width_row.setContentsMargins(0, 0, 0, 0)
        width_row.addWidget(QLabel(tr('너비')))
        self.width = QDoubleSpinBox()
        self.width.setRange(1, 1000)
        self.width.setSuffix(' mm')
        self.width.valueChanged.connect(self.resize_selected)
        width_row.addWidget(self.width)
        row.addWidget(width_group)
        self.remove_button = QPushButton(tr('선택한 직인 삭제'))
        set_action_icon(self.remove_button, 'delete')
        self.remove_button.clicked.connect(self.remove_selected)
        row.addWidget(self.remove_button)
        viewer.layout().insertWidget(2, self.panel)
        self.panel.hide()

    def choose_image(self):
        name, _ = QFileDialog.getOpenFileName(self.viewer, tr('직인 및 서명 이미지 선택'), '', tr('이미지 (*.png *.jpg *.jpeg)'))
        if name:
            try:
                self.add_image(name)
            except Exception as error:
                QMessageBox.warning(self.viewer, tr('직인 이미지 열기 실패'), str(error))

    def choose_vault(self):
        from .seal_vault_ui import SealVaultDialog
        dialog = SealVaultDialog(self.viewer)
        if dialog.exec() == QDialog.Accepted:
            try:
                self.add_image(dialog.selected_path)
            except Exception as error:
                QMessageBox.warning(self.viewer, tr('직인 이미지 열기 실패'), str(error))

    def add_image(self, path):
        if len(self.stamps) >= 64:
            raise ValueError(tr('직인은 한 번에 64개까지 배치할 수 있습니다. 저장한 뒤 계속해 주세요.'))
        stream, aspect = prepare_image(path)
        identity = hashlib.sha256(stream).digest()
        if identity not in self.image_cache:
            history = getattr(self.viewer, 'edit_history', None)
            previous = history.find_image(identity) if history else None
            if previous:
                stream, pixmap = previous.stream, previous.pixmap
            else:
                pixmap = QPixmap()
                if not pixmap.loadFromData(stream, 'PNG'):
                    raise ValueError(tr('미리보기를 만들 수 없습니다.'))
                pixmap = pixmap.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            size = len(stream) + pixmap.width() * pixmap.height() * 4
            retained = history.image_bytes(self.snapshot()) if history else self.image_bytes
            increment = 0 if previous else size
            if retained + increment > 96 * 1024 * 1024:
                raise ValueError(tr('이미지 메모리 한도에 도달했습니다. 저장한 뒤 계속해 주세요.'))
            self.image_cache[identity] = (stream, pixmap)
            self.image_bytes += size
        stream, pixmap = self.image_cache[identity]
        width, height = self.viewer.visible_page_size
        center = self.viewer.canvas.mapFrom(self.viewer.scroll.viewport(), self.viewer.scroll.viewport().rect().center())
        center_x = center.x() * width / max(1, self.viewer.canvas.width())
        center_y = center.y() * height / max(1, self.viewer.canvas.height())
        stamp_width = min(30 * UNIT, width / 3, height * aspect / 3)
        stamp = DraftStamp(self.viewer.pages[self.viewer.page.value() - 1], stream, pixmap, aspect,
                           center_x - stamp_width / 2, center_y - stamp_width / aspect / 2, stamp_width, width, height, identity)
        stamp.fit()
        self.viewer.begin_edit()
        self.stamps.append(stamp)
        self.viewer.table_copy_button.setChecked(False)
        self.select(stamp)
        self.changed('직인 추가')

    def visible_stamps(self):
        page = self.viewer.pages[self.viewer.page.value() - 1]
        return [stamp for stamp in self.stamps if stamp.page == page]

    def select(self, stamp):
        self.selected = stamp
        self.width.blockSignals(True)
        self.width.setEnabled(stamp is not None)
        self.remove_button.setEnabled(stamp is not None)
        if stamp:
            self.width.setMaximum(min(1000, stamp.page_width / UNIT, stamp.page_height * stamp.aspect / UNIT))
            self.width.setValue(stamp.width / UNIT)
        self.width.blockSignals(False)
        self.overlay.update()

    def resize_selected(self, value):
        if self.selected:
            self.viewer.begin_edit()
            self.selected.width = value * UNIT
            self.selected.fit()
            self.changed('직인 크기 조절')

    def remove_selected(self):
        if self.selected is not None:
            self.viewer.begin_edit()
            self.stamps.remove(self.selected)
            self.select(None)
            self.changed('직인 삭제')

    def changed(self, label='', *, record=True):
        self.select(self.selected)
        self.refresh()
        if record:
            self.viewer.record_edit(label or '직인 편집')
        else:
            self.viewer.update_dirty_state()

    def begin_gesture(self, label):
        self.viewer.begin_edit()
        self.gesture_label = label

    def finish_gesture(self):
        if self.gesture_label:
            label, self.gesture_label = self.gesture_label, None
            self.viewer.record_edit(label)

    def snapshot(self):
        from .edit_history import StampState
        return tuple(StampState(stamp.page, stamp.stream, stamp.pixmap,
                                stamp.image_key, stamp.aspect,
                                stamp.x, stamp.y, stamp.width, stamp.page_width, stamp.page_height)
                     for stamp in self.stamps)

    def restore(self, states, selected_index=-1):
        self.gesture_label = None
        self.overlay.drag = None
        self.overlay.auto_scroll.stop()
        self.stamps = [DraftStamp(stamp.page, stamp.stream, stamp.pixmap, stamp.aspect,
                                  stamp.x, stamp.y, stamp.width, stamp.page_width, stamp.page_height, stamp.image_key)
                       for stamp in states]
        self.image_cache = {stamp.image_key: (stamp.stream, stamp.pixmap) for stamp in states}
        self.image_bytes = sum(len(stream) + pixmap.width() * pixmap.height() * 4
                               for stream, pixmap in self.image_cache.values())
        self.select(self.stamps[selected_index] if 0 <= selected_index < len(self.stamps) else None)
        self.refresh()

    def release_unused_images(self):
        self.image_cache = {stamp.image_key: (stamp.stream, stamp.pixmap) for stamp in self.stamps}
        self.image_bytes = sum(len(stream) + pixmap.width() * pixmap.height() * 4
                               for stream, pixmap in self.image_cache.values())

    def refresh(self):
        self.stamps[:] = [stamp for stamp in self.stamps if stamp.page in self.viewer.pages]
        if self.selected not in self.stamps:
            self.select(None)
        self.panel.setVisible(bool(self.stamps))
        self.overlay.setGeometry(self.viewer.canvas.rect())
        self.overlay.setVisible(bool(self.visible_stamps()))
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents, self.viewer.table_copy_button.isChecked())
        self.overlay.raise_()
        self.overlay.update()

    def apply(self, document, pages):
        for stamp in self.stamps:
            if stamp.page in pages:
                place_prepared(document[pages.index(stamp.page)], stamp.stream, stamp.aspect,
                               stamp.x / UNIT, stamp.y / UNIT, stamp.width / UNIT)

    def reset(self):
        self.gesture_label = None
        self.stamps.clear()
        self.image_cache.clear()
        self.image_bytes = 0
        self.select(None)
        self.panel.hide()
        self.overlay.hide()
