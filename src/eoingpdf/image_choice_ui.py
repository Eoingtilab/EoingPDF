"""Background image inventory and visual choice of the original raster image."""
from .localization import tr
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
from .core import open_pdf
from .image_replace import inventory


class InventoryWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, path, password, parent):
        super().__init__(parent)
        self.path, self.password = path, password

    def run(self):
        try:
            with open_pdf(self.path, self.password) as document:
                result = inventory(document, self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.ready.emit(result)
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.password = ''


class ImageChoiceDialog(QDialog):
    def __init__(self, path, password='', parent=None):
        super().__init__(parent)
        self.selected = None
        self.closing = False
        self.setWindowTitle(tr('교체할 원본 이미지 선택'))
        self.resize(550, 580)
        layout = QVBoxLayout(self)
        self.status = QLabel(tr('문서의 이미지를 확인하고 있습니다.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.items = QListWidget()
        self.items.setIconSize(QSize(140, 100))
        layout.addWidget(self.items)
        self.use = QPushButton(tr('이 이미지와 같은 이미지 모두 교체'))
        self.use.setEnabled(False)
        self.use.clicked.connect(self.choose)
        layout.addWidget(self.use)
        close = QPushButton(tr('닫기'))
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.worker = InventoryWorker(path, password, self)
        self.worker.ready.connect(self.populate)
        self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(self.finished_scan)
        self.worker.start()

    def populate(self, entries):
        groups = {}
        for entry in entries:
            if entry['digest'] not in groups:
                groups[entry['digest']] = dict(entry, pages=set(entry['pages']))
            else:
                groups[entry['digest']]['pages'].update(entry['pages'])
        for entry in groups.values():
            pixmap = QPixmap()
            pixmap.loadFromData(entry['preview'], 'PNG')
            pages = ', '.join(str(page + 1) for page in sorted(entry['pages'])[:20])
            if len(entry['pages']) > 20:
                pages += tr(' 외')
            item = QListWidgetItem(QIcon(pixmap), tr('{v0} × {v1} 픽셀\n페이지: {v2}', v0=entry['width'], v1=entry['height'], v2=pages))
            item.setData(Qt.UserRole, (entry['xref'], entry['digest']))
            self.items.addItem(item)
        self.status.setText(tr('이미지 {v0}종을 찾았습니다. 교체할 이미지를 선택해 주세요.', v0=len(groups)) if groups else
                            tr('교체 가능한 이미지가 없습니다. 벡터 로고와 인라인 이미지는 지원하지 않습니다.'))
        if groups:
            self.items.setCurrentRow(0)

    def finished_scan(self):
        if self.closing:
            super().reject()
        else:
            self.use.setEnabled(self.items.count() > 0)

    def choose(self):
        item = self.items.currentItem()
        if item is not None and not self.worker.isRunning():
            self.selected = item.data(Qt.UserRole)
            self.accept()

    def reject(self):
        if self.worker.isRunning():
            self.closing = True
            self.worker.requestInterruption()
            self.status.setText(tr('확인을 중단하고 있습니다.'))
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.reject()
            event.ignore()
        else:
            event.accept()
