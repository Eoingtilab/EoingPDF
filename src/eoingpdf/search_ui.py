"""On-demand folder search UI backed by an isolated ONNX worker."""
import hashlib
import json
import os
from pathlib import Path
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QProgressBar, QFileDialog, QMessageBox, QCheckBox)
from .search_worker import SearchWorker
from .sdk_theme import apply_style
from .localization import tr


class SearchDialog(QDialog):
    def __init__(self, parent=None, *, model_folder=None, cache_folder=None):
        super().__init__(parent)
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        self.model_folder = Path(model_folder or root / 'assets/search')
        self.cache_folder = Path(cache_folder or Path(os.environ['LOCALAPPDATA']) / 'EoingPDF/search')
        self.worker = None
        self.viewer = None
        self.pending_close = False
        self.indexed_folder = None
        self.setWindowTitle(tr('어잉PDF · 문서 검색'))
        self.resize(760, 590)
        apply_style(self, 'QDialog {background:#f7f9fc;}')
        layout = QVBoxLayout(self)
        self.folder = QLineEdit()
        self.folder.setReadOnly(True)
        self.folder.setPlaceholderText(tr('검색할 PDF 폴더를 선택해 주세요'))
        self.choose_button = QPushButton(tr('폴더 선택'))
        self.choose_button.clicked.connect(self.choose_folder)
        row = QHBoxLayout(); row.addWidget(self.folder, 1); row.addWidget(self.choose_button)
        layout.addLayout(row)
        self.ocr_checkbox = QCheckBox(tr('스캔 PDF 글자 인식 포함 · 시간이 더 걸릴 수 있습니다'))
        layout.addWidget(self.ocr_checkbox)
        self.ocr_checkbox.toggled.connect(self.text_policy_changed)
        self.query = QLineEdit()
        self.query.setMaxLength(2000)
        self.query.setPlaceholderText(tr('찾고 싶은 내용을 문장으로 입력하세요'))
        self.query.returnPressed.connect(self.search)
        self.search_button = QPushButton(tr('검색'))
        self.choose_button.setAutoDefault(False)
        self.search_button.setAutoDefault(False)
        self.search_button.clicked.connect(self.search)
        row = QHBoxLayout(); row.addWidget(self.query, 1); row.addWidget(self.search_button)
        layout.addLayout(row)
        self.results = QListWidget()
        self.results.setWordWrap(True)
        self.results.itemDoubleClicked.connect(self.open_result)
        layout.addWidget(self.results, 1)
        self.status = QLabel(tr('문서와 검색 자료는 이 PC에만 저장됩니다.'))
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.hide(); layout.addWidget(self.progress)
        self.refresh_button = QPushButton(tr('폴더 다시 읽기'))
        self.refresh_button.clicked.connect(self.build)
        self.delete_button = QPushButton(tr('검색 자료 삭제'))
        self.delete_button.clicked.connect(self.delete_index)
        self.open_button = QPushButton(tr('선택한 페이지 열기'))
        self.open_button.clicked.connect(lambda: self.open_result(self.results.currentItem()))
        self.cancel_button = QPushButton(tr('작업 취소'))
        self.cancel_button.clicked.connect(self.cancel)
        row = QHBoxLayout()
        for button in (self.refresh_button, self.delete_button, self.open_button, self.cancel_button):
            button.setAutoDefault(False)
            row.addWidget(button)
        layout.addLayout(row)
        self.set_busy(False)

    def database(self):
        name = hashlib.sha256(str(Path(self.folder.text()).resolve()).casefold().encode('utf-8')).hexdigest()
        return self.cache_folder / (name + '.sqlite3')

    def text_policy_changed(self):
        self.indexed_folder = None
        self.results.clear()
        self.set_busy(self.worker is not None)

    def set_busy(self, busy):
        self.choose_button.setEnabled(not busy)
        self.ocr_checkbox.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy and bool(self.folder.text()))
        self.delete_button.setEnabled(not busy and bool(self.folder.text()) and self.database().is_file())
        self.search_button.setEnabled(not busy and self.indexed_folder == self.folder.text())
        self.query.setEnabled(not busy)
        self.results.setEnabled(not busy)
        self.open_button.setEnabled(not busy and self.results.count() > 0)
        self.cancel_button.setEnabled(busy)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr('검색할 폴더 선택'), self.folder.text())
        if folder:
            self.folder.setText(str(Path(folder).resolve()))
            self.indexed_folder = None
            self.build()

    def delete_index(self):
        if self.worker is not None or not self.folder.text():
            return
        if QMessageBox.question(self, tr('검색 자료 삭제'),
                tr('선택한 폴더의 검색용 텍스트와 색인을 이 PC에서 삭제할까요?\n원본 PDF는 유지됩니다.'),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            from .search_staging import delete_index
            delete_index(self.database(), self.cache_folder)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr('검색 자료 삭제 실패'), tr(str(error)))
            return
        self.indexed_folder = None
        self.results.clear()
        self.query.clear()
        self.status.setToolTip('')
        self.status.setText(tr('검색 자료를 삭제했습니다. 다시 검색하려면 폴더 다시 읽기를 눌러 주세요.'))
        self.set_busy(False)

    def build(self):
        if self.folder.text():
            self.start('build')

    def search(self):
        if self.query.text().strip() and self.indexed_folder == self.folder.text():
            self.start('search')

    def start(self, mode):
        if self.worker is not None:
            return
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        self.results.clear()
        self.status.setText(tr('폴더의 PDF를 읽고 있습니다.' if mode == 'build' else '문서에서 찾고 있습니다.'))
        self.progress.setRange(0, 100 if mode == 'build' else 0)
        self.progress.setValue(0); self.progress.show()
        options = dict(mode=mode, folder=self.folder.text(), database=str(self.database()),
                       model_folder=str(self.model_folder), query=self.query.text().strip(), use_ocr=self.ocr_checkbox.isChecked())
        worker = self.worker = SearchWorker(options, self)
        worker.progress.connect(self.progress.setValue)
        worker.result.connect(lambda ok, message: self.completed(mode, ok, message))
        worker.finished.connect(self.job_finished)
        self.set_busy(True)
        worker.start()

    def completed(self, mode, success, message):
        if self.pending_close:
            return
        if not success:
            self.status.setText(tr(message))
            return
        try:
            result = json.loads(message)
            if mode == 'build':
                self.indexed_folder = self.folder.text()
                self.status.setText(tr('PDF {files}개 확인 · 새로 읽음 {updated}개 · 제외 {errors}개',
                    files=result['files'], updated=result['updated'], errors=result['error_count']))
                self.status.setToolTip('\n'.join(f"{Path(item['path']).name}: {item['message']}" for item in result['errors']))
            else:
                for entry in result:
                    item = QListWidgetItem(tr('{file} · {page}페이지\n{snippet}',
                        file=Path(entry['path']).name, page=entry['page'] + 1, snippet=entry['text'].strip()))
                    item.setData(Qt.UserRole, entry)
                    self.results.addItem(item)
                if result:
                    self.results.setCurrentRow(0)
                self.status.setText(tr('{count}개 구간을 찾았습니다.', count=len(result)) if result else
                    tr('결과가 없습니다. 문서가 변경됐다면 폴더를 다시 읽어 주세요.'))
        except (ValueError, KeyError, TypeError):
            self.results.clear()
            self.status.setText(tr('검색 결과를 읽지 못했습니다. 다시 시도해 주세요.'))

    def job_finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.progress.hide()
        self.set_busy(False)
        if self.pending_close:
            self.close()

    def cancel(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.status.setText(tr('작업을 취소하고 있습니다.'))
            self.cancel_button.setEnabled(False)

    def open_result(self, item):
        if item is None or self.worker is not None:
            return
        try:
            if self.viewer is not None and not self.viewer.close():
                return
            from .viewer import PdfViewer
            viewer = PdfViewer(item.data(Qt.UserRole)['path'], self)
            try:
                viewer.show_search_result(item.data(Qt.UserRole))
            except Exception:
                viewer.close(); viewer.deleteLater()
                raise
            if self.viewer is not None:
                self.viewer.deleteLater()
            self.viewer = viewer
            viewer.show()
        except Exception as error:
            QMessageBox.warning(self, tr('검색 결과 열기 실패'), tr(str(error)))

    def reject(self):
        self.close()

    def showEvent(self, event):
        if self.worker is None:
            self.pending_close = False
        super().showEvent(event)

    def closeEvent(self, event):
        if self.worker is not None:
            self.pending_close = True
            self.cancel()
            event.ignore()
            return
        if self.viewer is not None and not self.viewer.close():
            self.pending_close = False
            event.ignore()
            return
        super().reject()
        event.accept()
