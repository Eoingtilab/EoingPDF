"""Session-only clipboard image collection; no clipboard history or resident watcher."""
import hashlib
import os
from pathlib import Path
import tempfile
import sys

from PySide6.QtCore import QObject, Signal, QEvent, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox)

from .localization import tr


class CaptureSession(QObject):
    changed = Signal()
    MAX_BYTES = 32 * 1024 * 1024
    MAX_IMAGES = 16

    def __init__(self, app):
        super().__init__(app)
        self.images = []
        self.bytes_used = 0
        self.last_digest = None
        self.listeners = 0
        self.clipboard = app.clipboard()

    def acquire(self):
        if self.listeners == 0:
            self.clipboard.dataChanged.connect(self.capture)
        self.listeners += 1

    def release(self):
        if not self.listeners:
            return
        self.listeners -= 1
        if self.listeners == 0:
            self.clipboard.dataChanged.disconnect(self.capture)
            self.clear()

    def clear(self):
        self.images.clear()
        self.bytes_used = 0
        self.last_digest = None
        self.changed.emit()

    def capture(self):
        mime = self.clipboard.mimeData()
        if mime is not None and mime.hasImage():
            self.add_image(self.clipboard.image())

    def add_image(self, image):
        if image.isNull() or image.width() * image.height() * 4 > self.MAX_BYTES:
            return False
        image = image.convertToFormat(QImage.Format_RGBA8888)
        digest = hashlib.sha256(image.constBits()).digest()
        identity = (image.width(), image.height(), digest)
        if identity == self.last_digest:
            return False
        size = image.sizeInBytes()
        while self.images and (len(self.images) >= self.MAX_IMAGES or self.bytes_used + size > self.MAX_BYTES):
            self.bytes_used -= self.images.pop(0).sizeInBytes()
        self.images.append(image.copy())
        self.bytes_used += size
        self.last_digest = identity
        self.changed.emit()
        return True


def session():
    app = QApplication.instance()
    if not hasattr(app, 'eoing_captures'):
        app.eoing_captures = CaptureSession(app)
    return app.eoing_captures


def save_captures(images, destination):
    """One image per PDF page, with no overwrite and no intermediate image files."""
    import pymupdf as pdf
    destination = Path(destination)
    if not images:
        raise ValueError(tr('저장할 캡처가 없습니다.'))
    if destination.exists():
        raise FileExistsError(tr('같은 이름의 파일이 있습니다. 다른 이름을 선택해 주세요.'))
    descriptor, temporary = tempfile.mkstemp(prefix='.eoing-capture-', suffix='.pdf', dir=destination.parent)
    os.close(descriptor)
    try:
        with pdf.open() as document:
            for image in images:
                if image.isNull():
                    raise ValueError(tr('읽을 수 없는 캡처 이미지입니다.'))
                buffer = QBuffer()
                buffer.open(QIODevice.WriteOnly)
                if not image.save(buffer, 'PNG'):
                    raise ValueError(tr('캡처 이미지를 변환하지 못했습니다.'))
                # Treat screen pixels as 96 DPI; cap the PDF's maximum page size.
                scale = min(.75, 14400 / max(image.width(), image.height()))
                page = document.new_page(width=image.width() * scale, height=image.height() * scale)
                page.insert_image(page.rect, stream=bytes(buffer.data()))
            document.save(temporary, deflate=True)
        # Atomic publication without replacing a file created while the dialog was open.
        if sys.platform == 'win32':
            os.rename(temporary, destination)
        else:
            os.link(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


class CaptureDialog(QDialog):
    discarded = Signal()

    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('캡처 모아 PDF'))
        self.resize(520, 430)
        layout = QVBoxLayout(self)
        notice = QLabel(tr('이미지를 끌어 순서를 바꾸거나 제외한 뒤 저장하세요. 한 이미지가 한 페이지가 됩니다.'))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.files = QListWidget()
        self.files.setDragDropMode(QListWidget.InternalMove)
        for index, image in enumerate(images):
            item = QListWidgetItem(QIcon(QPixmap.fromImage(image.scaled(96, 72, Qt.KeepAspectRatio))),
                                   tr('캡처 {number}', number=index + 1))
            item.setData(Qt.UserRole, image)
            self.files.addItem(item)
        layout.addWidget(self.files)
        row = QHBoxLayout()
        remove = QPushButton(tr('선택 제거'))
        remove.clicked.connect(self.remove_selected)
        row.addWidget(remove)
        clear = QPushButton(tr('캡처 모두 비우기'))
        clear.clicked.connect(self.clear_captures)
        row.addWidget(clear)
        row.addStretch()
        self.save_button = QPushButton(tr('PDF 저장'))
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.save_button)
        close = QPushButton(tr('닫기'))
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)

    def remove_selected(self):
        if self.files.currentRow() >= 0:
            self.files.takeItem(self.files.currentRow())
        self.save_button.setEnabled(self.files.count() > 0)

    def clear_captures(self):
        self.files.clear()
        self.save_button.setEnabled(False)
        self.discarded.emit()

    def save(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        name, _ = QFileDialog.getSaveFileName(self, tr('PDF 저장'), 'captures.pdf', 'PDF (*.pdf)')
        if not name:
            return
        if Path(name).suffix.lower() != '.pdf':
            name += '.pdf'
        try:
            save_captures([self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())], name)
        except Exception as error:
            QMessageBox.warning(self, tr('저장 실패'), str(error))
            return
        self.accept()


class CaptureChip(QPushButton):
    """A hidden chip still observes its owning window's show/hide lifecycle."""
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        self.store = session()
        self.lease = [False]
        store, lease = self.store, self.lease
        def detached(*_):
            if lease[0]:
                lease[0] = False
                store.release()
        self.detach = detached
        window.destroyed.connect(detached)
        window.installEventFilter(self)
        self.store.changed.connect(self.refresh)
        self.clicked.connect(self.open_captures)
        self.hide()
        self.setToolTip(tr('앱 창이 열린 동안의 클립보드 이미지만 보관합니다. 최대 16개·32MB이며 오래된 이미지부터 제외합니다.'))

    def eventFilter(self, watched, event):
        if watched is getattr(self, 'owner', None):
            if event.type() == QEvent.Show and not self.lease[0]:
                self.lease[0] = True
                self.store.acquire()
                self.refresh()
            elif event.type() == QEvent.Hide:
                self.detach()
        return super().eventFilter(watched, event)

    def refresh(self):
        count = len(self.store.images)
        self.setText(tr('캡처 {count}개 · PDF로 묶기', count=count))
        self.setVisible(count >= 2)

    def open_captures(self):
        snapshot = list(self.store.images)
        dialog = CaptureDialog(snapshot, self.owner)
        dialog.discarded.connect(self.store.clear)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            saved_keys = {image.cacheKey() for image in snapshot}
            self.store.images = [image for image in self.store.images if image.cacheKey() not in saved_keys]
            self.store.bytes_used = sum(image.sizeInBytes() for image in self.store.images)
            self.store.last_digest = None
            self.store.changed.emit()
