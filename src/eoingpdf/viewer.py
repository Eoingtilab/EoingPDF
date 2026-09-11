"""Read-only PDF reader. Render one page at a time with bounded memory."""
from pathlib import Path
import pymupdf as pdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox, QComboBox, QScrollArea, QInputDialog, QFileDialog, QMessageBox
from .core import open_pdf, pages_from_text, Request, run


def delete_pages(path, selection, folder):
    with open_pdf(path) as document:
        removed = set(pages_from_text(selection, document.page_count))
        kept = [str(index + 1) for index in range(document.page_count) if index not in removed]
    if not kept:
        raise ValueError('모든 페이지를 삭제할 수 없습니다. 한 페이지 이상 남겨 주세요.')
    return run(Request('extract', (str(path),), str(folder), ','.join(kept)))


class PdfViewer(QDialog):
    def __init__(self, path, parent=None, page=0):
        super().__init__(parent)
        self.path = Path(path)
        with open_pdf(self.path) as document:
            self.count = document.page_count
        self.setWindowTitle(f'{self.path.name} · 어잉PDF')
        self.resize(960, 820)
        self.setStyleSheet('QDialog {background:#f7f9fc;} QScrollArea {background:#e8edf5;border:0;}')
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        open_button = QPushButton('PDF 열기')
        open_button.clicked.connect(self.choose_pdf)
        delete_button = QPushButton('페이지 삭제')
        delete_button.clicked.connect(self.remove_pages)
        bar.addWidget(open_button)
        bar.addWidget(delete_button)
        self.previous = QPushButton('‹ 이전')
        self.next = QPushButton('다음 ›')
        self.page = QSpinBox()
        self.page.setRange(1, self.count)
        self.page.setValue(max(1, min(page + 1, self.count)))
        self.page.setSuffix(f' / {self.count}')
        self.zoom = QComboBox()
        self.zoom.addItems(['너비 맞춤', '50%', '75%', '100%', '125%', '150%', '200%'])
        bar.addWidget(QLabel('페이지'))
        bar.addWidget(self.page)
        bar.addWidget(self.previous)
        bar.addWidget(self.next)
        bar.addStretch()
        bar.addWidget(self.zoom)
        layout.addLayout(bar)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel('읽기 전용 · 원본은 수정하지 않습니다')
        layout.addWidget(self.status)
        self.previous.clicked.connect(lambda: self.page.setValue(self.page.value() - 1))
        self.next.clicked.connect(lambda: self.page.setValue(self.page.value() + 1))
        self.page.valueChanged.connect(self.render)
        self.zoom.currentIndexChanged.connect(self.render)
        for key, delta in [('PgDown', 1), ('PgUp', -1)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda d=delta: self.page.setValue(self.page.value() + d))
        self.render()

    def choose_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, 'PDF 열기', str(self.path.parent), 'PDF (*.pdf)')
        if path:
            try:
                self.load(path)
            except Exception as error:
                QMessageBox.warning(self, 'PDF 열기 실패', str(error))

    def load(self, path):
        with open_pdf(path) as document:
            count = document.page_count
        self.path, self.count = Path(path), count
        self.setWindowTitle(f'{self.path.name} · 어잉PDF')
        self.page.blockSignals(True)
        self.page.setRange(1, count)
        self.page.setValue(1)
        self.page.setSuffix(f' / {count}')
        self.page.blockSignals(False)
        self.render()

    def remove_pages(self):
        selection, accepted = QInputDialog.getText(self, '페이지 삭제', '삭제할 페이지 (예: 3, 7-9)\n원본은 보존하고 새 PDF로 저장합니다.', text=str(self.page.value()))
        if not accepted or not selection.strip():
            return
        try:
            with open_pdf(self.path) as document:
                removed = set(pages_from_text(selection, document.page_count))
                if len(removed) == document.page_count:
                    raise ValueError('한 페이지 이상 남겨 주세요.')
            folder = QFileDialog.getExistingDirectory(self, '새 PDF 저장 폴더', str(self.path.parent))
            if not folder:
                return
            result = delete_pages(self.path, selection, folder)
            self.load(result)
            self.status.setText(f'삭제 후 새 파일로 저장했어요: {result.name}')
        except Exception as error:
            QMessageBox.warning(self, '페이지 삭제 실패', str(error))

    def render(self, *_):
        try:
            with open_pdf(self.path) as document:
                page = document[self.page.value() - 1]
                scale = max(100, self.scroll.viewport().width() - 30) / page.rect.width if self.zoom.currentIndex() == 0 else int(self.zoom.currentText()[:-1]) / 100
                # A huge page must not allocate an unbounded raster.
                scale = min(scale, 5000 / max(page.rect.width, page.rect.height))
                raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                self.canvas.setPixmap(QPixmap.fromImage(image))
                self.canvas.resize(raster.width, raster.height)
            self.previous.setEnabled(self.page.value() > 1)
            self.next.setEnabled(self.page.value() < self.count)
            self.scroll.verticalScrollBar().setValue(0)
            self.status.setText('읽기 전용 · 원본은 수정하지 않습니다')
        except Exception as error:
            self.canvas.clear()
            self.status.setText(f'페이지를 열지 못했습니다: {error}')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'scroll') and self.zoom.currentIndex() == 0:
            self.render()
