"""Review detected AcroForm rectangles before creating any output file."""
from .localization import tr
import pymupdf as pdf
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QComboBox)
from .core import open_pdf
from .forms import candidates


class CandidateScan(QThread):
    result = Signal(object, str)

    def __init__(self, path, password, parent):
        super().__init__(parent)
        self.path, self.password = path, password

    def run(self):
        try:
            found = []
            with open_pdf(self.path, self.password) as document:
                for index, page in enumerate(document):
                    if self.isInterruptionRequested():
                        return
                    for rect, kind in candidates(page):
                        found.append(dict(page=index, rect=list(rect), kind=kind))
                        if len(found) > 2000:
                            raise ValueError(tr('입력 칸이 2,000개를 초과합니다. 문서를 나누어 주세요.'))
            self.result.emit(found, '')
        except Exception as error:
            self.result.emit([], str(error))
        finally:
            self.password = ''


class FormReviewDialog(QDialog):
    def __init__(self, path, password='', parent=None):
        super().__init__(parent)
        self.path, self.password = path, password
        self.closing = False
        self.setWindowTitle(tr('입력 칸 감지 결과 검토'))
        self.resize(920, 720)
        layout = QVBoxLayout(self)
        self.status = QLabel(tr('입력 칸을 찾고 있습니다. 잘못 감지된 칸은 체크를 해제하세요.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.items = QListWidget()
        self.items.setMaximumWidth(280)
        row.addWidget(self.items)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(300, 350)
        row.addWidget(self.preview, 1)
        layout.addLayout(row, 1)
        self.kind = QComboBox()
        self.kind.addItem(tr('텍스트 입력 칸'), 'text')
        self.kind.addItem(tr('체크 칸'), 'checkbox')
        self.kind.setEnabled(False)
        self.kind.activated.connect(self.change_kind)
        layout.addWidget(self.kind)
        buttons = QHBoxLayout()
        for label, state in [(tr('모두 선택'), Qt.Checked), (tr('모두 제외'), Qt.Unchecked)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, value=state: self.select_all(value))
            buttons.addWidget(button)
        self.apply = QPushButton(tr('선택한 입력 칸 생성'))
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.accept)
        buttons.addWidget(self.apply)
        cancel = QPushButton(tr('취소'))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.items.currentRowChanged.connect(self.show_candidate)
        self.items.itemChanged.connect(self.update_selection)
        self.scan = CandidateScan(path, password, self)
        self.scan.result.connect(self.scanned)
        self.scan.finished.connect(self.scan_finished)
        self.scan.start()

    def scanned(self, entries, error):
        if self.closing:
            return
        if error:
            self.status.setText(tr('감지 실패: ') + error)
            return
        self.items.blockSignals(True)
        for index, entry in enumerate(entries):
            item = QListWidgetItem(tr('{v0}페이지 · 입력 칸 {v1}', v0=entry["page"] + 1, v1=index + 1))
            item.setData(Qt.UserRole, entry)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.items.addItem(item)
        self.items.blockSignals(False)
        self.update_selection()
        if entries:
            self.items.setCurrentRow(0)
        else:
            self.status.setText(tr('빈 입력 칸을 찾지 못했습니다. 스캔 이미지의 칸은 자동 감지하지 않습니다.'))

    def selection(self):
        return [dict(self.items.item(i).data(Qt.UserRole)) for i in range(self.items.count())
                if self.items.item(i).checkState() == Qt.Checked]

    def update_selection(self, *_):
        count = len(self.selection())
        self.apply.setEnabled(count > 0)
        self.status.setText(tr('{v0}개 감지 · {v1}개 생성 예정. 파란 테두리의 위치와 칸 종류를 확인하세요.', v0=self.items.count(), v1=count))

    def select_all(self, state):
        self.items.blockSignals(True)
        for index in range(self.items.count()):
            self.items.item(index).setCheckState(state)
        self.items.blockSignals(False)
        self.update_selection()

    def change_kind(self, *_):
        item = self.items.currentItem()
        if item is not None:
            entry = item.data(Qt.UserRole)
            entry['kind'] = self.kind.currentData()
            item.setData(Qt.UserRole, entry)

    def show_candidate(self, index):
        item = self.items.item(index)
        if item is None:
            return
        entry = item.data(Qt.UserRole)
        self.kind.setEnabled(True)
        self.kind.setCurrentIndex(self.kind.findData(entry['kind']))
        try:
            with open_pdf(self.path, self.password) as document:
                page = document[entry['page']]
                page.draw_rect(pdf.Rect(entry['rect']), color=(.15, .35, 1), width=2)
                scale = min(max(1, self.preview.width()) / page.rect.width,
                            max(1, self.preview.height()) / page.rect.height, 2)
                raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                self.preview.setPixmap(QPixmap.fromImage(image))
        except Exception as error:
            self.preview.clear()
            self.status.setText(tr('미리보기 실패: ') + str(error))

    def accept(self):
        if self.selection() and not self.scan.isRunning():
            super().accept()

    def reject(self):
        if self.scan.isRunning():
            self.closing = True
            self.scan.requestInterruption()
            self.status.setText(tr('감지를 취소하고 있습니다.'))
            self.apply.setEnabled(False)
            return
        super().reject()

    def scan_finished(self):
        if self.closing:
            super().reject()

    def closeEvent(self, event):
        if self.scan.isRunning():
            self.reject()
            event.ignore()
        else:
            event.accept()
