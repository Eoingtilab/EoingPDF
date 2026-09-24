"""Read-only PDF reader. Render one page at a time with bounded memory."""
from .localization import tr
from .sdk_theme import apply_style
from pathlib import Path
import pymupdf as pdf
from PySide6.QtCore import Qt, QEvent, QTimer, QSize, QPoint, Signal, QRectF
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence, QIcon, QGuiApplication
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox, QComboBox, QInputDialog, QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QListView, QWidget, QAbstractSpinBox, QLineEdit
from .core import open_pdf, pages_from_text, Request, run


def delete_pages(path, selection, folder):
    with open_pdf(path) as document:
        removed = set(pages_from_text(selection, document.page_count))
        kept = [str(index + 1) for index in range(document.page_count) if index not in removed]
    if not kept:
        raise ValueError(tr('모든 페이지를 삭제할 수 없습니다. 한 페이지 이상 남겨 주세요.'))
    return run(Request('extract', (str(path),), str(folder), ','.join(kept)))


class PdfOpenCancelled(ValueError):
    """User cancelled password entry; leave any existing document intact."""


def unlock_viewer_pdf(path, parent=None, password=''):
    """Authenticate in memory; never create a decrypted temporary document."""
    with pdf.open(path) as document:
        if not document.is_pdf or not document.page_count:
            raise ValueError(tr('페이지가 있는 PDF 파일을 선택해 주세요.'))
        while document.needs_pass and not document.authenticate(password):
            password, accepted = QInputDialog.getText(
                parent, tr('PDF 암호 입력'),
                tr('문서를 열기 위한 암호를 입력해 주세요. 암호는 저장하지 않습니다.'),
                QLineEdit.Password)
            if not accepted:
                raise PdfOpenCancelled(tr('PDF 열기를 취소했습니다.'))
            if not document.authenticate(password):
                QMessageBox.warning(parent, tr('암호 확인'), tr('암호가 맞지 않습니다. 다시 입력해 주세요.'))
        return password, document.page_count


class PdfViewer(QDialog):
    def __init__(self, path, parent=None, page=0):
        super().__init__(parent)
        self.path = Path(path)
        self.password, self.count = unlock_viewer_pdf(self.path, self)
        self.pages = list(range(self.count))
        self.dirty = False
        self.search_hit = None
        self.slideshow = None
        self.setWindowTitle(tr('{v0} · 어잉PDF', v0=self.path.name))
        self.resize(960, 820)
        self.setMinimumSize(680, 480)
        apply_style(self, 'QDialog {background:#f7f9fc;} QScrollArea {background:#e8edf5;border:0;} QListWidget {background:#eef2f8;border:0;color:#263246;} QListWidget::item:selected {background:#dbe6ff;border:2px solid #5176ec;border-radius:6px;} QSpinBox, QComboBox {background:white;color:#263246;border:1px solid #dae2f0;border-radius:6px;padding:7px;min-width:75px;}')
        layout = QVBoxLayout(self)
        from .capture_ui import CaptureChip
        self.capture_chip = CaptureChip(self)
        layout.addWidget(self.capture_chip)
        bar = QHBoxLayout()
        navigation = QHBoxLayout()
        open_button = QPushButton(tr('PDF 열기'))
        open_button.clicked.connect(self.choose_pdf)
        delete_button = QPushButton(tr('페이지 삭제'))
        delete_button.clicked.connect(self.remove_pages)
        slideshow_button = QPushButton(tr('슬라이드쇼 · F5'))
        slideshow_button.clicked.connect(self.start_slideshow)
        bar.addWidget(open_button)
        bar.addWidget(delete_button)
        bar.addWidget(slideshow_button)
        self.save_button = QPushButton(tr('저장'))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_changes)
        bar.addWidget(self.save_button)
        self.previous = QPushButton(tr('‹ 이전'))
        self.next = QPushButton(tr('다음 ›'))
        self.page = QSpinBox()
        self.page.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.page.setRange(1, self.count)
        self.page.setValue(max(1, min(page + 1, self.count)))
        self.page.setSuffix(f' / {self.count}')
        self.zoom = QComboBox()
        apply_style(self.zoom, 'QComboBox {background:#ffffff;color:#263246;} QComboBox QAbstractItemView {background:#ffffff;color:#263246;selection-background-color:#dbe6ff;selection-color:#183b8f;border:1px solid #dae2f0;outline:0;} QComboBox QAbstractItemView::item {min-height:28px;padding:4px 8px;}')
        self.zoom.addItems([tr('너비 맞춤'), '50%', '75%', '100%', '125%', '150%', '200%'])
        navigation.addWidget(self.previous)
        navigation.addWidget(QLabel(tr('페이지')))
        navigation.addWidget(self.page)
        step_controls = QVBoxLayout()
        step_controls.setSpacing(0)
        for text, delta in [('▲', 1), ('▼', -1)]:
            step = QPushButton(text)
            step.setAutoDefault(False)
            step.setFixedSize(28, 20)
            apply_style(step, 'QPushButton {padding:0;color:#263246;background:white;border:1px solid #dae2f0;border-radius:3px;font-size:12px;}')
            step.setToolTip(tr('다음 페이지') if delta > 0 else tr('이전 페이지'))
            step.clicked.connect(lambda checked=False, d=delta: self.page.stepBy(d))
            step_controls.addWidget(step)
        navigation.addLayout(step_controls)
        navigation.addWidget(self.next)
        navigation.addStretch()
        navigation.addWidget(self.zoom)
        from PySide6.QtWidgets import QMenu
        self.print_button = QPushButton(tr('인쇄 준비'))
        print_menu = QMenu(self.print_button)
        for title, action in [(tr('밝은 인쇄용 사본'), 'print_light'), (tr('4쪽 모아찍기'), 'four_up'), (tr('소책자 인쇄 배치'), 'booklet')]:
            item = print_menu.addAction(tr(title))
            item.triggered.connect(lambda checked=False, key=action: self.diagnostic_action(key))
        print_menu.aboutToShow.connect(lambda: self.sniffer.start(self.path, trigger='print'))
        self.print_button.setMenu(print_menu)
        navigation.addWidget(self.print_button)
        bar.addStretch()
        self.close_button = QPushButton(tr('닫기'))
        self.close_button.clicked.connect(self.close)
        bar.addWidget(self.close_button)
        from .license_ui import settings
        license_button = QPushButton(tr('라이선스'))
        license_button.clicked.connect(lambda: settings(self))
        from .updates import show_update_status
        update_button = QPushButton(tr('업데이트'))
        update_button.clicked.connect(lambda: show_update_status(self))
        layout.addLayout(bar)
        from .sniffer_ui import MicroSniffer, DiagnosticChips
        self.sniffer = MicroSniffer(self)
        self.chips = DiagnosticChips(self)
        self.sniffed_path = None
        self.sniffer.result.connect(self.chips.display)
        self.chips.action.connect(self.diagnostic_action)
        layout.addWidget(self.chips)
        from .page_scroll import PageScrollArea
        self.scroll = PageScrollArea()
        self.scroll.page_requested.connect(self.scroll_page)
        self._wheel_bottom_page = None
        self.scroll.interacted.connect(self.clear_scroll_landing)
        self.scroll.verticalScrollBar().sliderMoved.connect(self.clear_scroll_landing)
        self.scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        from .selection_canvas import SelectionCanvas
        self.canvas = SelectionCanvas()
        self.canvas.selected.connect(self.copy_selected_table)
        self.canvas.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.canvas)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.render)
        self.scroll.viewport().installEventFilter(self)
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
        layout.addLayout(navigation)
        self.status = QLabel(tr('읽기 전용 · 원본은 수정하지 않습니다'))
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.restore_status)
        footer = QHBoxLayout()
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.copy_image_button = QPushButton(tr('페이지 이미지 복사'))
        self.copy_image_button.setToolTip(tr('현재 페이지를 300DPI로 복사'))
        self.copy_image_button.clicked.connect(self.copy_page_image)
        footer.addWidget(self.copy_image_button)
        self.table_copy_button = QPushButton(tr('표 드래그 복사'))
        self.table_copy_button.setCheckable(True)
        self.table_copy_button.toggled.connect(self.canvas.set_selecting)
        footer.addWidget(self.table_copy_button)
        self.form_button = QPushButton(tr('양식 입력'))
        self.form_button.clicked.connect(self.edit_form)
        footer.addWidget(self.form_button)
        footer.addWidget(license_button)
        footer.addWidget(update_button)
        layout.addLayout(footer)
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
        QShortcut(QKeySequence('Shift+F5'), self).activated.connect(self.start_slideshow)
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self.save_changes)

    def start_slideshow(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if self.slideshow is not None and self.slideshow.isVisible():
            self.slideshow.raise_()
            self.slideshow.activateWindow()
            return
        self.slideshow = SlideShow(self.path, self.page.value() - 1, self, self.pages, password=self.password)
        self.slideshow.setWindowModality(Qt.WindowModal)
        slides = self.slideshow
        slides.finished.connect(lambda _: self.finish_slideshow(slides))
        screens = QGuiApplication.screens()
        main_screen = self.screen()
        secondary = next((screen for screen in screens if screen != main_screen), None)
        if secondary is not None:
            slides.winId()
            slides.windowHandle().setScreen(secondary)
            slides.setGeometry(secondary.geometry())
            slides.setWindowModality(Qt.NonModal)
            slides.exit_button.hide()
            slides.presenter_button.hide()
            slides.hint.hide()
        self.slideshow.showFullScreen()
        self.slideshow.activateWindow()
        self.slideshow.setFocus()
        if secondary is not None:
            slides.show_presenter(main_screen)

    def copy_page_image(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        try:
            from .clipboard_tools import copy_page
            with open_pdf(self.path, self.password) as doc:
                copy_page(doc[self.pages[self.page.value() - 1]], int(self.winId()))
            self.show_feedback(tr('300DPI 페이지 이미지를 복사했습니다.'))
        except Exception as error:
            self.show_feedback(tr('이미지 복사 실패: {error}', error=tr(str(error))))

    def copy_selected_table(self, rect):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        try:
            from .clipboard_tools import selection_rect, extract_table, copy_table
            with open_pdf(self.path, self.password) as doc:
                page = doc[self.pages[self.page.value() - 1]]
                clip = selection_rect(page, (rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height()),
                                      (self.canvas.width(), self.canvas.height()))
                rows = extract_table(page, clip)
                copy_table(rows, int(self.winId()))
            self.show_feedback(tr('{count}행 표를 복사했습니다. Excel에 붙여넣을 수 있습니다.', count=len(rows)))
        except Exception as error:
            self.show_feedback(tr('표 복사 실패: {error}', error=tr(str(error))))

    def show_feedback(self, message):
        self.status.setText(message)
        self.feedback_timer.start(5000)

    def restore_status(self):
        self.status.setText(tr('저장하지 않은 변경이 있어요 · 저장 버튼으로 새 PDF를 만드세요') if self.dirty else tr('원본은 수정하지 않습니다'))

    def diagnostic_action(self, action):
        if action == 'rename':
            name = self.chips.suggested_name
            if name and Path(name).name == name and not any(c in name for c in '<>:"/\\|?*'):
                self.save_changes(suggested_name=name)
        elif action == 'presentation':
            self.start_slideshow()
        elif action == 'table':
            self.table_copy_button.setChecked(True)
            self.show_feedback(tr('복사할 표 전체를 마우스로 드래그해 주세요.'))
        else:
            if self.dirty:
                answer = QMessageBox.question(self, tr('변경 사항 저장'),
                    tr('보조 도구를 사용하려면 페이지 변경 사항을 먼저 저장해야 합니다. 새 PDF로 저장할까요?'),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if answer != QMessageBox.Yes or not self.save_changes():
                    return
            from .advanced_ui import AdvancedDialog
            dialog = AdvancedDialog(self)
            dialog.source.setText(str(self.path))
            dialog.password.setText(self.password)
            dialog.tool.setCurrentIndex(dialog.tool.findData(action))
            dialog.exec()

    def edit_form(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if self.dirty:
            answer = QMessageBox.question(self, tr('변경 사항 저장'),
                tr('양식을 입력하기 전에 페이지 변경 사항을 새 PDF로 저장할까요?'),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer != QMessageBox.Yes or not self.save_changes():
                return
        try:
            from .form_ui import FormDialog
            dialog = FormDialog(self.path, self.pages[self.page.value() - 1], self, password=self.password)
            dialog.saved.connect(self.load)
            dialog.exec()
        except Exception as error:
            QMessageBox.warning(self, tr('양식 입력 실패'), str(error))

    def finish_slideshow(self, slides):
        self.page.setValue(slides.viewer_indices[slides.index] + 1)
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
            with open_pdf(self.path, self.password) as document:
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
                    remove.setToolTip(tr('{page}페이지 삭제', page=index + 1))
                    remove.setFixedSize(24, 24)
                    apply_style(remove, 'QPushButton {padding:0;background:#fff;color:#b33445;border:1px solid #e2d5d9;border-radius:5px;}')
                    remove.clicked.connect(lambda checked=False, row=index: self.stage_delete({row}))
                    header.addWidget(remove)
                    card_layout.addLayout(header)
                    thumbnail = QPushButton()
                    thumbnail.setObjectName('thumbnailPage')
                    thumbnail.setIcon(QIcon(QPixmap.fromImage(image)))
                    thumbnail.setIconSize(QSize(112, 144))
                    apply_style(thumbnail, 'QPushButton {padding:0;border:0;background:transparent;}')
                    thumbnail.clicked.connect(lambda checked=False, row=index: self.page.setValue(row + 1))
                    card_layout.addWidget(thumbnail)
                    self.thumbnails.setItemWidget(self.thumbnails.item(index), card)
                    self.thumbnail_cache.add(index)
            if len(pending) > 4:
                self.thumbnail_timer.start(30)
        except Exception:
            pass  # Main page reports a useful error if the source disappears.

    def choose_pdf(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if not self.confirm_leave():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('PDF 열기'), str(self.path.parent), 'PDF (*.pdf)')
        if path:
            try:
                self.load(path)
            except PdfOpenCancelled:
                return
            except Exception as error:
                QMessageBox.warning(self, tr('PDF 열기 실패'), str(error))

    def load(self, path, password=''):
        password, count = unlock_viewer_pdf(path, self, password)
        self.password = password
        self.search_hit = None
        self.path, self.count = Path(path), count
        self.sniffed_path = None
        self.chips.hide()
        self.sniffer.start(self.path)
        self.sniffed_path = self.path
        self.pages = list(range(count))
        self.dirty = False
        self.save_button.setEnabled(False)
        self.setWindowTitle(tr('{v0} · 어잉PDF', v0=self.path.name))
        self.page.blockSignals(True)
        self.page.setRange(1, count)
        self.page.setValue(1)
        self.page.setSuffix(f' / {count}')
        self.page.blockSignals(False)
        self.reset_thumbnails()
        self.render()

    def show_search_result(self, result):
        import math
        from .semantic_search import fingerprint
        if Path(result['path']).resolve() != self.path.resolve():
            raise ValueError(tr('검색 결과와 열린 문서가 다릅니다.'))
        if fingerprint(self.path) != result['digest']:
            raise ValueError(tr('검색 후 문서가 변경되었습니다. 폴더를 다시 색인해 주세요.'))
        index = result['page']
        if type(index) is not int or index not in self.pages:
            raise ValueError(tr('검색 결과 페이지를 찾을 수 없습니다.'))
        coordinates = result['rect']
        if len(coordinates) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coordinates):
            raise ValueError(tr('검색 결과 영역이 올바르지 않습니다.'))
        with open_pdf(self.path, self.password) as document:
            area = pdf.Rect(coordinates)
            visible = area * document[index].rotation_matrix
            if area.is_empty or not document[index].rect.intersects(visible):
                raise ValueError(tr('검색 결과 영역이 페이지 밖에 있습니다.'))
        self.search_hit = (index, tuple(coordinates))
        self.page.setValue(self.pages.index(index) + 1)
        self.render()
        self.show_feedback(tr('검색한 내용이 표시된 영역입니다.'))

    def remove_pages(self):
        selection, accepted = QInputDialog.getText(self, tr('페이지 삭제'), tr('삭제할 페이지 (예: 3, 7-9)\n마지막에 저장을 눌러 변경을 저장하세요.'), text=str(self.page.value()))
        if not accepted or not selection.strip():
            return
        try:
            self.stage_delete(set(pages_from_text(selection, self.count)))
        except Exception as error:
            QMessageBox.warning(self, tr('페이지 삭제 실패'), str(error))

    def stage_delete(self, removed):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if len(removed) >= self.count:
            QMessageBox.warning(self, tr('페이지 삭제'), tr('한 페이지 이상 남겨 주세요.'))
            return
        selected = ', '.join(str(i + 1) for i in sorted(removed))
        answer = QMessageBox.question(self, tr('페이지 삭제 확인'), tr('{pages}페이지를 삭제할까요?\n저장 전까지 원본 파일은 변경되지 않습니다.', pages=selected), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.pages = [page for index, page in enumerate(self.pages) if index not in removed]
        self.count = len(self.pages)
        self.dirty = True
        self.save_button.setEnabled(True)
        self.setWindowTitle(tr('* {v0} · 어잉PDF', v0=self.path.name))
        self.page.blockSignals(True)
        self.page.setRange(1, self.count)
        self.page.setSuffix(f' / {self.count}')
        self.page.blockSignals(False)
        self.reset_thumbnails()
        self.render()

    def save_changes(self, *, suggested_name=None):
        if not self.dirty and suggested_name is None:
            return True
        from .license_ui import ensure_license
        if not ensure_license(self):
            return False
        target, _ = QFileDialog.getSaveFileName(self, tr('추천 이름으로 사본 저장') if suggested_name else tr('편집한 PDF 저장'), str(self.path.with_name(suggested_name or self.path.stem + tr('_편집.pdf'))), 'PDF (*.pdf)')
        if not target:
            return False
        try:
            import tempfile
            from .jobs import publish
            target = Path(target)
            if target.suffix.lower() != '.pdf':
                target = target.with_suffix('.pdf')
            if target.resolve() == self.path.resolve():
                raise ValueError(tr('원본 보존을 위해 다른 파일 이름을 선택해 주세요.'))
            with tempfile.TemporaryDirectory(prefix='eoing-viewer-') as temporary:
                result = Path(temporary) / 'edited.pdf'
                with open_pdf(self.path, self.password) as document:
                    document.select(self.pages)
                    document.save(result, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_KEEP)
                with open_pdf(result, self.password) as check:
                    if check.page_count != len(self.pages):
                        raise ValueError(tr('저장한 페이지 수가 일치하지 않습니다.'))
                saved = publish(result, target.parent, target.name)
            self.load(saved, password=self.password)
            self.status.setText(tr('저장했어요: {file} · 원본 보존', file=saved.name))
            return True
        except Exception as error:
            QMessageBox.warning(self, tr('PDF 저장 실패'), str(error))
            return False

    def confirm_leave(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, tr('저장하지 않은 변경'), tr('페이지 삭제 내용을 저장할까요?'), QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
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
            self.feedback_timer.stop()
            self.sniffer.stop()
            super().reject()
            event.accept()
        else:
            event.ignore()

    def clear_scroll_landing(self, *_):
        self._wheel_bottom_page = None

    def scroll_page(self, delta):
        target = max(1, min(self.count, self.page.value() + delta))
        if target == self.page.value():
            return
        self._wheel_bottom_page = target if delta < 0 else None
        self.page.setValue(target)

    def render(self, *_):
        try:
            self.canvas.set_selecting(self.table_copy_button.isChecked())
            with open_pdf(self.path, self.password) as document:
                page = document[self.pages[self.page.value() - 1]]
                scale = max(100, self.scroll.viewport().width() - 30) / page.rect.width if self.zoom.currentIndex() == 0 else int(self.zoom.currentText()[:-1]) / 100
                # A huge page must not allocate an unbounded raster.
                scale = min(scale, 5000 / max(page.rect.width, page.rect.height))
                raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                self.canvas.setPixmap(QPixmap.fromImage(image))
                self.canvas.resize(raster.width, raster.height)
                self.canvas.set_search_highlight()
                if self.search_hit and self.search_hit[0] == self.pages[self.page.value() - 1]:
                    area = (pdf.Rect(self.search_hit[1]) * page.rotation_matrix) & page.rect
                    self.canvas.set_search_highlight(QRectF(
                        area.x0 / page.rect.width, area.y0 / page.rect.height,
                        area.width / page.rect.width, area.height / page.rect.height))
            self.previous.setEnabled(self.page.value() > 1)
            self.next.setEnabled(self.page.value() < self.count)
            scrollbar = self.scroll.verticalScrollBar()
            if self._wheel_bottom_page == self.page.value():
                scrollbar.setValue(scrollbar.maximum())
            else:
                self._wheel_bottom_page = None
                scrollbar.setValue(0)
                highlight = self.canvas.search_highlight
                if highlight is not None:
                    self.scroll.ensureVisible(round(highlight.center().x() * self.canvas.width()),
                                              round(highlight.center().y() * self.canvas.height()), 30, 30)
            if not self.feedback_timer.isActive():
                self.restore_status()
            self.thumbnails.blockSignals(True)
            self.thumbnails.setCurrentRow(self.page.value() - 1)
            self.thumbnails.scrollToItem(self.thumbnails.currentItem())
            self.thumbnails.blockSignals(False)
            self.thumbnail_timer.start(30)
        except Exception as error:
            self.canvas.clear()
            self.canvas.set_search_highlight()
            self.status.setText(tr('페이지를 열지 못했습니다: {error}', error=tr(str(error))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'scroll') and self.zoom.currentIndex() == 0:
            self.fit_timer.start(30)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_timer.start(0)
        if self.sniffed_path != self.path:
            self.sniffed_path = self.path
            self.sniffer.start(self.path)

    def eventFilter(self, watched, event):
        if hasattr(self, 'scroll') and watched is self.scroll.viewport() and event.type() == QEvent.Resize and self.zoom.currentIndex() == 0:
            self.fit_timer.start(30)
        return super().eventFilter(watched, event)


class SlideShow(QDialog):
    """Keyboard and mouse presentation without changing the PDF."""
    page_changed = Signal()
    def __init__(self, path, page=0, parent=None, pages=None, password=''):
        super().__init__(parent)
        self.path = Path(path)
        self.password = password
        with open_pdf(path, self.password) as document:
            self.pages = list(pages) if pages is not None else list(range(document.page_count))
            self.count = len(self.pages)
        self.index = max(0, min(page, self.count - 1))
        self.blank = None
        self.presenter = None
        self.grid = None
        self.reveal_steps = []
        self.reveal_index = -1
        self.ink_by_slide = {}
        self.boards = {}
        self.viewer_indices = list(range(self.count))
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(lambda: self.advance(1))
        self.setWindowTitle(tr('어잉PDF · 슬라이드쇼'))
        # Audience chrome has a fixed dark palette, independent of the app theme.
        # Do not send document-stage colors through the legacy SDK color mapper.
        self.setProperty('eoingAudience', True)
        self.setStyleSheet('''
            QDialog, QLabel {background:#111827;color:#dbe5f5;border:0;}
            QPushButton, QComboBox {
                background:#263246;color:#ffffff;border:1px solid #64748b;
                border-radius:6px;padding:8px 16px;font-size:15px;font-weight:400;
            }
            QPushButton:hover, QComboBox:hover {background:#405170;}
            QPushButton:checked {background:#405170;border:2px solid #a8c7ff;}
            QPushButton:focus, QComboBox:focus {border:2px solid #a8c7ff;}
            QComboBox QAbstractItemView {
                background:#263246;color:#ffffff;
                selection-background-color:#405170;selection-color:#ffffff;
            }
        ''')
        self.setFocusPolicy(Qt.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        controls = QHBoxLayout()
        controls.setContentsMargins(12, 8, 12, 0)
        controls.addStretch()
        self.presenter_button = QPushButton(tr('발표자 화면'))
        self.presenter_button.setAutoDefault(False)
        self.presenter_button.clicked.connect(lambda: self.show_presenter())
        controls.addWidget(self.presenter_button)
        self.ink_button = QPushButton(tr('판서 · P'))
        self.ink_button.setCheckable(True)
        self.ink_button.setAutoDefault(False)
        self.ink_button.toggled.connect(lambda checked: self.canvas.toggle_ink() if hasattr(self, 'canvas') and checked != self.canvas.ink_enabled else None)
        controls.addWidget(self.ink_button)
        self.ink_tools = QComboBox()
        for label, tool in [(tr('펜 · P'), 'pen'), (tr('형광펜 · H'), 'highlight'), (tr('임시 펜 · Ctrl+P'), 'ghost'), (tr('도형 보정 · Ctrl+D'), 'shape'), (tr('텍스트 · T'), 'text')]:
            self.ink_tools.addItem(label, tool)
        self.ink_tools.setToolTip(tr('형광펜: 텍스트 줄에 드래그 · 임시 펜: 3초 뒤 사라짐 · 도형: 원·사각형·화살표·별·체크 보정'))
        self.ink_tools.activated.connect(lambda _: self.select_ink_tool(self.ink_tools.currentData()))
        controls.addWidget(self.ink_tools)
        self.bake_button = QPushButton(tr('판서 저장'))
        self.bake_button.setAutoDefault(False)
        self.bake_button.clicked.connect(self.bake_annotations)
        controls.addWidget(self.bake_button)
        self.exit_button = QPushButton(tr('전체화면 종료 · Esc'))
        self.exit_button.setAutoDefault(False)
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.exit_button.clicked.connect(self.reject)
        controls.addWidget(self.exit_button)
        layout.addLayout(controls)
        from .presentation_canvas import PresentationCanvas
        self.canvas = PresentationCanvas()
        self.canvas.text_edit_started.connect(self.click_timer.stop)
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setMinimumSize(1, 1)
        self.canvas.installEventFilter(self)
        layout.addWidget(self.canvas, 1)
        self.hint = QLabel()
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.installEventFilter(self)
        layout.addWidget(self.hint)
        native_ink = self.canvas.enable_native_ink()
        if native_ink is not None:
            native_ink.failed.connect(lambda error: self.hint.setText(
                tr('고속 판서를 시작하지 못해 기본 판서로 전환했습니다. ') + error))

    def bake_annotations(self):
        if not self.canvas.commit_text():
            return False
        self.stash_surface()
        if not self.has_ink():
            QMessageBox.information(self, tr('판서 저장'), tr('저장할 판서가 없습니다.'))
            return False
        target, _ = QFileDialog.getSaveFileName(self, tr('판서 PDF 저장'),
                                                str(self.path.with_name(self.path.stem + tr('_판서.pdf'))),
                                                'PDF (*.pdf)')
        if not target:
            return False
        target = Path(target)
        if target.suffix.lower() != '.pdf':
            target = target.with_suffix('.pdf')
        if target.resolve() == self.path.resolve() or target.exists():
            QMessageBox.warning(self, tr('판서 저장'), tr('원본 또는 기존 파일은 덮어쓸 수 없습니다.'))
            return False
        try:
            from .presentation_ink import save_presentation_ink, board_order
            saved_boards = board_order(self.boards, self.count)
            save_presentation_ink(self.path, target, self.pages, self.ink_by_slide, self.password, self.boards)
            mapping = []
            next_index = 0
            for slide in range(self.count):
                if slide == self.index:
                    next_index = len(mapping)
                mapping.append(self.viewer_indices[slide])
                for key in saved_boards:
                    if key[0] == slide:
                        if slide == self.index and key[1] == self.blank:
                            next_index = len(mapping)
                        mapping.append(self.viewer_indices[slide])
            self.viewer_indices = mapping
            self.index = next_index
            self.count = len(mapping)
            self.blank = None
            self.boards.clear()
            # Continue from the saved document so another save cannot lose
            # previously committed ink or restore deleted viewer pages.
            self.path = target
            self.pages = list(range(self.count))
            self.ink_by_slide.clear()
            self.canvas.set_ink([])
            if self.grid is not None:
                self.grid.reject()
                self.grid.deleteLater()
                self.grid = None
            self.ink_button.setChecked(False)
            self.render()
            self.page_changed.emit()
            QMessageBox.information(self, tr('판서 저장 완료'), tr('{file}으로 저장했습니다.', file=target.name))
            return True
        except Exception as error:
            QMessageBox.warning(self, tr('판서 저장 실패'), str(error))
            return False

    def has_ink(self):
        from .ink_stroke import permanent
        return any(permanent(stroke) for strokes in
                   [self.canvas.ink_strokes, *self.ink_by_slide.values(),
                    *(board["strokes"] for board in self.boards.values())] for stroke in strokes)

    def select_ink_tool(self, tool):
        self.canvas.set_tool(tool)
        self.ink_tools.setCurrentIndex(self.ink_tools.findData(tool))
        self.ink_button.setChecked(True)

    def done(self, result):
        self.click_timer.stop()
        if not self.canvas.commit_text():
            return
        if self.has_ink():
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr('저장하지 않은 판서'))
            dialog.setText(tr('발표 중 작성한 판서를 저장할까요?'))
            save = dialog.addButton(tr('저장'), QMessageBox.AcceptRole)
            discard = dialog.addButton(tr('저장하지 않음'), QMessageBox.DestructiveRole)
            cancel = dialog.addButton(tr('취소'), QMessageBox.RejectRole)
            dialog.setDefaultButton(save)
            dialog.setEscapeButton(cancel)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is save:
                if not self.bake_annotations():
                    return
            elif clicked is not discard:
                return
        super().done(result)

    def render(self):
        try:
            if self.blank:
                self.canvas.mask_suspended = False
                self.canvas.board_mode = True
                width, height = self.boards[(self.index, self.blank)]['size']
                self.canvas.page_size = (width, height)
                self.canvas.text_lines = []
                ratio = self.devicePixelRatioF()
                scale = min(max(1, self.canvas.width()) / width, max(1, self.canvas.height()) / height)
                pixmap = QPixmap(max(1, round(width * scale * ratio)), max(1, round(height * scale * ratio)))
                pixmap.setDevicePixelRatio(ratio)
                self.canvas.setStyleSheet('background:' + self.blank + ';')
                self.canvas.ink_width = 2.5 * scale
                pixmap.fill(Qt.black if self.blank == 'black' else Qt.white)
                self.canvas.setPixmap(pixmap)
                name = tr('검은 칠판') if self.blank == 'black' else tr('흰 칠판')
                self.hint.setText(tr('{board} · P: 필기 · T: 텍스트 · B/W: 칠판 전환 · Space: 슬라이드 복귀 · 저장 시 별도 페이지 추가', board=name))
                return
            self.canvas.mask_suspended = False
            self.canvas.board_mode = False
            self.canvas.setStyleSheet('')
            with open_pdf(self.path, self.password) as document:
                page = document[self.pages[self.index]]
                # Display coordinates account for the PDF page's intrinsic rotation.
                self.canvas.page_size = (page.rect.width, page.rect.height)
                self.canvas.text_lines = []
                text = page.get_text('dict', flags=pdf.TEXTFLAGS_DICT & ~pdf.TEXT_PRESERVE_IMAGES)
                for block in text['blocks']:
                    for line in block.get('lines', []):
                        if any(span.get('text', '').strip() for span in line['spans']):
                            rect = (pdf.Rect(line['bbox']) * page.rotation_matrix) & page.rect
                            if not rect.is_empty:
                                self.canvas.text_lines.append(QRectF(rect.x0 / page.rect.width, rect.y0 / page.rect.height,
                                                                   rect.width / page.rect.width, rect.height / page.rect.height))
                ends = []
                for block in page.get_text('blocks'):
                    if block[6] == 0 and block[4].strip():
                        rect = pdf.Rect(block[:4]) * page.rotation_matrix
                        ends.append(min(1.0, max(0.0, (rect.y1 + 8) / page.rect.height)))
                self.reveal_steps = sorted(set(round(value, 4) for value in ends))
                ratio = self.devicePixelRatioF()
                scale = min(max(1, self.canvas.width()) / page.rect.width,
                            max(1, self.canvas.height()) / page.rect.height) * ratio
                scale = min(scale, 5000 / max(page.rect.width, page.rect.height))
                raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(image)
                pixmap.setDevicePixelRatio(ratio)
                self.canvas.setPixmap(pixmap)
                self.canvas.ink_width = 2.5 * pixmap.deviceIndependentSize().width() / page.rect.width
            self.hint.setText(tr('{page} / {total}   ·   Space: 문단 순서로 공개   ·   → / 클릭: 다음   ·   G: 페이지 목록   ·   Esc: 종료', page=self.index + 1, total=self.count))
        except Exception as error:
            self.canvas.clear()
            self.hint.setText(tr('페이지를 열지 못했습니다: {error} · Esc: 종료', error=tr(str(error))))

    def advance(self, delta):
        self.click_timer.stop()
        index = max(0, min(self.index + delta, self.count - 1))
        if index != self.index:
            if not self.canvas.commit_text():
                return
            self.stash_surface()
            self.index = index
            self.canvas.set_ink(self.ink_by_slide.setdefault(index, []))
            self.blank = None
            self.reveal_index = -1
            self.canvas.reveal_fraction = 1.0
            self.render()
            self.page_changed.emit()

    def stash_surface(self):
        if self.blank:
            self.boards[(self.index, self.blank)]['strokes'] = self.canvas.ink_strokes
        else:
            self.ink_by_slide[self.index] = self.canvas.ink_strokes

    def set_blank(self, color):
        if color not in ('black', 'white'):
            raise ValueError(tr('칠판 색상이 올바르지 않습니다.'))
        self.click_timer.stop()
        if not self.canvas.commit_text():
            return
        self.stash_surface()
        self.blank = None if self.blank == color else color
        if self.blank:
            board = self.boards.setdefault((self.index, self.blank), {
                'size': (720.0, 720.0 * max(1, self.canvas.height()) / max(1, self.canvas.width())),
                'strokes': []})
            self.canvas.set_ink(board['strokes'])
        else:
            self.canvas.set_ink(self.ink_by_slide.setdefault(self.index, []))
        self.render()

    def reveal_next(self):
        if self.blank:
            self.set_blank(self.blank)
            return
        if len(self.reveal_steps) <= 1 or self.reveal_index >= len(self.reveal_steps) - 1:
            self.advance(1)
            return
        self.reveal_index += 1
        self.canvas.reveal_fraction = (1.0 if self.reveal_index == len(self.reveal_steps) - 1
                                       else self.reveal_steps[self.reveal_index])
        self.canvas.update()

    def show_grid(self):
        from .slide_grid import SlideGrid
        if self.grid is None:
            self.grid = SlideGrid(self)
        self.grid.list.setCurrentRow(self.index)
        self.grid.show()
        self.grid.raise_()
        self.grid.activateWindow()

    def show_presenter(self, screen=None):
        from .presenter import PresenterHud
        if self.presenter is None:
            self.presenter = PresenterHud(self)
        if screen is not None:
            self.presenter.winId()
            self.presenter.windowHandle().setScreen(screen)
            self.presenter.move(screen.availableGeometry().topLeft())
        self.presenter.show()
        self.presenter.raise_()
        self.presenter.activateWindow()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_F5):
            self.reject()
        elif key == Qt.Key_B:
            self.set_blank('black')
        elif key == Qt.Key_W:
            self.set_blank('white')
        elif key == Qt.Key_G:
            self.show_grid()
        elif key == Qt.Key_S:
            self.canvas.toggle_spotlight()
        elif key == Qt.Key_L and event.modifiers() & Qt.ControlModifier:
            self.canvas.toggle_laser()
        elif key == Qt.Key_T:
            self.select_ink_tool('text')
        elif key == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            self.select_ink_tool('shape')
        elif key == Qt.Key_P and event.modifiers() & Qt.ControlModifier:
            self.select_ink_tool('ghost')
        elif key == Qt.Key_H:
            self.select_ink_tool('highlight')
        elif key == Qt.Key_P and self.canvas.ink_tool != 'pen':
            self.select_ink_tool('pen')
        elif key == Qt.Key_P:
            self.canvas.toggle_ink()
            if hasattr(self, 'ink_button'):
                self.ink_button.setChecked(self.canvas.ink_enabled)
        elif key == Qt.Key_Space and event.modifiers() & Qt.ShiftModifier:
            self.advance(-1)
        elif key == Qt.Key_Space:
            self.reveal_next()
        elif key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown, Qt.Key_Return, Qt.Key_Enter):
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
        if watched is self.canvas and event.type() == QEvent.MouseButtonDblClick:
            self.click_timer.stop()
            return False
        if event.type() == QEvent.MouseButtonPress:
            if watched is self.canvas and self.canvas.ink_enabled and event.button() == Qt.LeftButton:
                return False
            if watched is self.canvas and event.button() == Qt.LeftButton and self.canvas.page_rect().contains(event.position()):
                point = self.canvas._normalized(event.position())
                if not any(rect.contains(point) for rect in self.canvas.text_lines):
                    self.click_timer.start(QGuiApplication.styleHints().mouseDoubleClickInterval())
                    return True
            self.click_timer.stop()
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
