"""Transient, bounded thumbnail navigation for a running presentation."""
from .localization import tr
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QListView
import pymupdf as pdf
from .core import open_pdf
from .sdk_theme import apply_style


class SlideGrid(QDialog):
    def __init__(self, audience):
        parent = audience.presenter if audience.presenter and audience.presenter.isVisible() else audience
        super().__init__(parent)
        self.audience = audience
        self.loaded = set()
        self.setWindowTitle(tr('페이지 바로 이동 · G'))
        self.resize(860, 620)
        apply_style(self, '''
            QDialog, QListWidget {background:#f6f8fc;color:#193455;}
            QLabel {background:transparent;color:#193455;padding:8px;}
            QListWidget::item {background:white;color:#193455;border:1px solid #dbe5f5;border-radius:8px;}
            QListWidget::item:selected {background:#e4ebff;border:2px solid #4f6bff;}
        ''')
        layout = QVBoxLayout(self)
        self.status = QLabel(tr('클릭 또는 방향키·Enter로 이동 · Esc: 돌아가기'))
        layout.addWidget(self.status)
        self.list = QListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Static)
        self.list.setUniformItemSizes(True)
        self.list.setIconSize(QSize(160, 120))
        self.list.setGridSize(QSize(185, 160))
        self.list.setSpacing(4)
        layout.addWidget(self.list)
        for index, original in enumerate(audience.pages):
            item = QListWidgetItem(tr('{v0} · 원본 {v1}쪽', v0=index + 1, v1=original + 1))
            item.setSizeHint(QSize(180, 150))
            self.list.addItem(item)
        self.list.setCurrentRow(audience.index)
        self.list.itemClicked.connect(self.select_page)
        self.list.itemActivated.connect(self.select_page)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.load_visible)
        self.list.verticalScrollBar().valueChanged.connect(lambda _: self.timer.start(30))
        audience.finished.connect(lambda _: self.reject())

    def select_page(self, item):
        self.audience.advance(self.list.row(item) - self.audience.index)
        self.accept()

    def load_visible(self):
        if not self.isVisible():
            return
        viewport = self.list.viewport().rect()
        visible = [index for index in range(self.list.count())
                   if self.list.visualItemRect(self.list.item(index)).intersects(viewport)]
        # Release off-screen pixmaps: memory does not grow with pages visited.
        keep = set(visible)
        for index in self.loaded - keep:
            self.list.item(index).setIcon(QIcon())
        self.loaded.intersection_update(keep)
        pending = [index for index in visible if index not in self.loaded]
        try:
            with open_pdf(self.audience.path, self.audience.password) as document:
                for index in pending[:2]:
                    page = document[self.audience.pages[index]]
                    scale = min(160 / page.rect.width, 120 / page.rect.height)
                    raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                    image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                    self.list.item(index).setIcon(QIcon(QPixmap.fromImage(image)))
                    self.loaded.add(index)
            if len(pending) > 2:
                self.timer.start(0)
        except Exception as error:
            self.status.setText(tr('미리보기를 읽지 못했습니다: {v0}', v0=error))

    def showEvent(self, event):
        super().showEvent(event)
        self.list.scrollToItem(self.list.currentItem())
        self.list.setFocus()
        self.timer.start(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'timer'):
            self.timer.start(30)

    def done(self, result):
        self.timer.stop()
        for index in self.loaded:
            self.list.item(index).setIcon(QIcon())
        self.loaded.clear()
        super().done(result)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_G:
            self.reject()
        else:
            super().keyPressEvent(event)
