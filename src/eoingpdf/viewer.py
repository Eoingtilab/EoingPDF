"""Read-only PDF reader. Render one page at a time with bounded memory."""
from pathlib import Path
import pymupdf as pdf
from PySide6.QtCore import Qt, QEvent, QTimer, QSize, QPoint
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence, QIcon
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox, QComboBox, QScrollArea, QInputDialog, QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QListView, QWidget
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
        self.pages = list(range(self.count))
        self.dirty = False
        self.slideshow = None
        self.setWindowTitle(f'{self.path.name} · 어잉PDF')
        self.resize(960, 820)
        self.setStyleSheet('QDialog {background:#f7f9fc;} QScrollArea {background:#e8edf5;border:0;} QListWidget {background:#eef2f8;border:0;color:#263246;} QListWidget::item:selected {background:#dbe6ff;border:2px solid #5176ec;border-radius:6px;} QSpinBox, QComboBox {background:white;color:#263246;border:1px solid #dae2f0;border-radius:6px;padding:7px;min-width:75px;}')
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        open_button = QPushButton('PDF 열기')
        open_button.clicked.connect(self.choose_pdf)
        delete_button = QPushButton('페이지 삭제')
        delete_button.clicked.connect(self.remove_pages)
        slideshow_button = QPushButton('슬라이드쇼 · F5')
        slideshow_button.clicked.connect(self.start_slideshow)
        bar.addWidget(open_button)
        bar.addWidget(delete_button)
        bar.addWidget(slideshow_button)
        self.save_button = QPushButton('저장')
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_changes)
        bar.addWidget(self.save_button)
        self.previous = QPushButton('‹ 이전')
        self.next = QPushButton('다음 ›')
        self.page = QSpinBox()
        self.page.setRange(1, self.count)
        self.page.setValue(max(1, min(page + 1, self.count)))
        self.page.setSuffix(f' / {self.count}')
        self.zoom = QComboBox()
        self.zoom.setStyleSheet('QComboBox {background:#ffffff;color:#263246;} QComboBox QAbstractItemView {background:#ffffff;color:#263246;selection-background-color:#dbe6ff;selection-color:#183b8f;border:1px solid #dae2f0;outline:0;} QComboBox QAbstractItemView::item {min-height:28px;padding:4px 8px;}')
        self.zoom.addItems(['너비 맞춤', '50%', '75%', '100%', '125%', '150%', '200%'])
        bar.addWidget(QLabel('페이지'))
        bar.addWidget(self.page)
        bar.addWidget(self.previous)
        bar.addWidget(self.next)
        bar.addStretch()
        bar.addWidget(self.zoom)
        self.close_button = QPushButton('닫기')
        self.close_button.clicked.connect(self.close)
        bar.addWidget(self.close_button)
        layout.addLayout(bar)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.canvas)
        body = QHBoxLayout()
        self.thumbnails = QListWidget()
        self.thumbnails.setFixedWidth(156)
        self.thumbnails.setViewMode(QListView.IconMode)
        self.thumbnails.setMovement(QListView.Static)
        self.thumbnails.setWrapping(False)
        self.thumbnails.setFlow(QListView.TopToBottom)
        self.thumbnails.setIconSize(QSize(112, 144))
        self.thumbnails.setSpacing(5)
        self.thumbnails.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setSingleShot(True)
        self.thumbnail_timer.timeout.connect(self.fill_thumbnails)
        self.thumbnails.verticalScrollBar().valueChanged.connect(lambda: self.thumbnail_timer.start(30))
        self.thumbnails.currentRowChanged.connect(lambda row: self.page.setValue(row + 1) if row >= 0 else None)
        body.addWidget(self.thumbnails)
        body.addWidget(self.scroll, 1)
        layout.addLayout(body, 1)
        self.status = QLabel('읽기 전용 · 원본은 수정하지 않습니다')
        layout.addWidget(self.status)
        self.previous.clicked.connect(lambda: self.page.setValue(self.page.value() - 1))
        self.next.clicked.connect(lambda: self.page.setValue(self.page.value() + 1))
        self.page.valueChanged.connect(self.render)
        self.zoom.currentIndexChanged.connect(self.render)
        for key, delta in [('PgDown', 1), ('PgUp', -1)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda d=delta: self.page.setValue(self.page.value() + d))
        self.reset_thumbnails()
        self.render()
        QShortcut(QKeySequence('F5'), self).activated.connect(self.start_slideshow)
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self.save_changes)

    def start_slideshow(self):
        if self.slideshow is not None and self.slideshow.isVisible():
            self.slideshow.raise_()
            self.slideshow.activateWindow()
            return
        self.slideshow = SlideShow(self.path, self.page.value() - 1, self, self.pages)
        self.slideshow.setWindowModality(Qt.WindowModal)
        slides = self.slideshow
        slides.finished.connect(lambda _: self.finish_slideshow(slides))
        self.slideshow.showFullScreen()
        self.slideshow.activateWindow()
        self.slideshow.setFocus()

    def finish_slideshow(self, slides):
        self.page.setValue(slides.index + 1)
        self.raise_()
        self.activateWindow()
        self.page.setFocus()

    def reset_thumbnails(self):
        self.thumbnails.blockSignals(True)
        self.thumbnails.clear()
        self.thumbnail_cache = set()
        for index in range(self.count):
            item = QListWidgetItem()
            item.setSizeHint(QSize(128, 180))
            item.setTextAlignment(Qt.AlignHCenter)
            self.thumbnails.addItem(item)
        self.thumbnails.setCurrentRow(self.page.value() - 1)
        self.thumbnails.blockSignals(False)
        self.thumbnail_timer.start(30)

    def fill_thumbnails(self):
        viewport = self.thumbnails.viewport()
        first = max(0, self.thumbnails.indexAt(QPoint(10, 10)).row())
        last = self.thumbnails.indexAt(QPoint(10, max(10, viewport.height() - 10))).row()
        if last < first:
            last = min(self.count - 1, first + max(2, viewport.height() // 174 + 1))
        pending = [i for i in range(max(0, first - 1), min(self.count, last + 2)) if i not in self.thumbnail_cache]
        try:
            with open_pdf(self.path) as document:
                for index in pending[:4]:
                    page = document[self.pages[index]]
                    scale = min(112 / page.rect.width, 144 / page.rect.height)
                    raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                    image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                    card = QWidget()
                    card_layout = QVBoxLayout(card)
                    card_layout.setContentsMargins(3, 2, 3, 2)
                    card_layout.setSpacing(2)
                    header = QHBoxLayout()
                    header.addWidget(QLabel(str(index + 1)))
                    header.addStretch()
                    remove = QPushButton('×')
                    remove.setObjectName('deleteThumbnail')
                    remove.setToolTip(f'{index + 1}페이지 삭제')
                    remove.setFixedSize(24, 24)
                    remove.setStyleSheet('QPushButton {padding:0;background:#fff;color:#b33445;border:1px solid #e2d5d9;border-radius:5px;}')
                    remove.clicked.connect(lambda checked=False, row=index: self.stage_delete({row}))
                    header.addWidget(remove)
                    card_layout.addLayout(header)
                    thumbnail = QPushButton()
                    thumbnail.setObjectName('thumbnailPage')
                    thumbnail.setIcon(QIcon(QPixmap.fromImage(image)))
                    thumbnail.setIconSize(QSize(112, 144))
                    thumbnail.setStyleSheet('QPushButton {padding:0;border:0;background:transparent;}')
                    thumbnail.clicked.connect(lambda checked=False, row=index: self.page.setValue(row + 1))
                    card_layout.addWidget(thumbnail)
                    self.thumbnails.setItemWidget(self.thumbnails.item(index), card)
                    self.thumbnail_cache.add(index)
            if len(pending) > 4:
                self.thumbnail_timer.start(30)
        except Exception:
            pass  # Main page reports a useful error if the source disappears.

    def choose_pdf(self):
        if not self.confirm_leave():
            return
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
        self.pages = list(range(count))
        self.dirty = False
        self.save_button.setEnabled(False)
        self.setWindowTitle(f'{self.path.name} · 어잉PDF')
        self.page.blockSignals(True)
        self.page.setRange(1, count)
        self.page.setValue(1)
        self.page.setSuffix(f' / {count}')
        self.page.blockSignals(False)
        self.reset_thumbnails()
        self.render()

    def remove_pages(self):
        selection, accepted = QInputDialog.getText(self, '페이지 삭제', '삭제할 페이지 (예: 3, 7-9)\n마지막에 저장을 눌러 변경을 저장하세요.', text=str(self.page.value()))
        if not accepted or not selection.strip():
            return
        try:
            self.stage_delete(set(pages_from_text(selection, self.count)))
        except Exception as error:
            QMessageBox.warning(self, '페이지 삭제 실패', str(error))

    def stage_delete(self, removed):
        if len(removed) >= self.count:
            QMessageBox.warning(self, '페이지 삭제', '한 페이지 이상 남겨 주세요.')
            return
        selected = ', '.join(str(i + 1) for i in sorted(removed))
        answer = QMessageBox.question(self, '페이지 삭제 확인', f'{selected}페이지를 삭제할까요?\n저장 전까지 원본 파일은 변경되지 않습니다.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.pages = [page for index, page in enumerate(self.pages) if index not in removed]
        self.count = len(self.pages)
        self.dirty = True
        self.save_button.setEnabled(True)
        self.setWindowTitle(f'* {self.path.name} · 어잉PDF')
        self.page.blockSignals(True)
        self.page.setRange(1, self.count)
        self.page.setSuffix(f' / {self.count}')
        self.page.blockSignals(False)
        self.reset_thumbnails()
        self.render()

    def save_changes(self):
        if not self.dirty:
            return True
        target, _ = QFileDialog.getSaveFileName(self, '편집한 PDF 저장', str(self.path.with_name(self.path.stem + '_편집.pdf')), 'PDF (*.pdf)')
        if not target:
            return False
        try:
            import tempfile
            from .jobs import publish
            target = Path(target)
            if target.suffix.lower() != '.pdf':
                target = target.with_suffix('.pdf')
            if target.resolve() == self.path.resolve():
                raise ValueError('원본 보존을 위해 다른 파일 이름을 선택해 주세요.')
            with tempfile.TemporaryDirectory(prefix='eoing-viewer-') as temporary:
                result = run(Request('extract', (str(self.path),), temporary, ','.join(str(i + 1) for i in self.pages)))
                saved = publish(result, target.parent, target.name)
            self.load(saved)
            self.status.setText(f'저장했어요: {saved.name} · 원본 보존')
            return True
        except Exception as error:
            QMessageBox.warning(self, 'PDF 저장 실패', str(error))
            return False

    def confirm_leave(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, '저장하지 않은 변경', '페이지 삭제 내용을 저장할까요?', QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            return self.save_changes()
        return answer == QMessageBox.Discard

    def reject(self):
        self.close()

    def closeEvent(self, event):
        if self.confirm_leave():
            if self.slideshow is not None and self.slideshow.isVisible():
                self.slideshow.reject()
            self.thumbnail_timer.stop()
            super().reject()
            event.accept()
        else:
            event.ignore()

    def render(self, *_):
        try:
            with open_pdf(self.path) as document:
                page = document[self.pages[self.page.value() - 1]]
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
            self.status.setText('저장하지 않은 변경이 있어요 · 저장 버튼으로 새 PDF를 만드세요' if self.dirty else '원본은 수정하지 않습니다')
            self.thumbnails.blockSignals(True)
            self.thumbnails.setCurrentRow(self.page.value() - 1)
            self.thumbnails.scrollToItem(self.thumbnails.currentItem())
            self.thumbnails.blockSignals(False)
            self.thumbnail_timer.start(30)
        except Exception as error:
            self.canvas.clear()
            self.status.setText(f'페이지를 열지 못했습니다: {error}')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'scroll') and self.zoom.currentIndex() == 0:
            self.render()


class SlideShow(QDialog):
    """Keyboard and mouse presentation without changing the PDF."""
    def __init__(self, path, page=0, parent=None, pages=None):
        super().__init__(parent)
        self.path = Path(path)
        with open_pdf(path) as document:
            self.pages = list(pages) if pages is not None else list(range(document.page_count))
            self.count = len(self.pages)
        self.index = max(0, min(page, self.count - 1))
        self.setWindowTitle('어잉PDF · 슬라이드쇼')
        self.setStyleSheet('QDialog, QLabel {background:#111827;color:#dbe5f5;border:0;}')
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(self.styleSheet() + ' QPushButton {font-size:15px;font-weight:400;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        controls = QHBoxLayout()
        controls.setContentsMargins(12, 8, 12, 0)
        controls.addStretch()
        self.exit_button = QPushButton('전체화면 종료 · Esc')
        self.exit_button.setAutoDefault(False)
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.exit_button.setStyleSheet('QPushButton {background:#263246;color:white;border:1px solid #64748b;border-radius:6px;padding:8px 16px;} QPushButton:hover {background:#405170;}')
        self.exit_button.clicked.connect(self.reject)
        controls.addWidget(self.exit_button)
        layout.addLayout(controls)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setMinimumSize(1, 1)
        self.canvas.installEventFilter(self)
        layout.addWidget(self.canvas, 1)
        self.hint = QLabel()
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.installEventFilter(self)
        layout.addWidget(self.hint)

    def render(self):
        try:
            with open_pdf(self.path) as document:
                page = document[self.pages[self.index]]
                ratio = self.devicePixelRatioF()
                scale = min(max(1, self.canvas.width()) / page.rect.width,
                            max(1, self.canvas.height()) / page.rect.height) * ratio
                scale = min(scale, 5000 / max(page.rect.width, page.rect.height))
                raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(image)
                pixmap.setDevicePixelRatio(ratio)
                self.canvas.setPixmap(pixmap)
            self.hint.setText(f'{self.index + 1} / {self.count}   ·   Space / 클릭: 다음   ·   ← / 오른쪽 클릭: 이전   ·   Esc: 종료')
        except Exception as error:
            self.canvas.clear()
            self.hint.setText(f'페이지를 열지 못했습니다: {error} · Esc: 종료')

    def advance(self, delta):
        index = max(0, min(self.index + delta, self.count - 1))
        if index != self.index:
            self.index = index
            self.render()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_F5):
            self.reject()
        elif key == Qt.Key_Space and event.modifiers() & Qt.ShiftModifier:
            self.advance(-1)
        elif key in (Qt.Key_Space, Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown, Qt.Key_Return, Qt.Key_Enter):
            self.advance(1)
        elif key in (Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp, Qt.Key_Backspace):
            self.advance(-1)
        elif key == Qt.Key_Home:
            self.advance(-self.count)
        elif key == Qt.Key_End:
            self.advance(self.count)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.advance(1)
        elif event.button() == Qt.RightButton:
            self.advance(-1)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress:
            self.mousePressEvent(event)
            return True
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.render()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'canvas'):
            self.render()
