"""Non-destructive overlay and before/after slider for two PDF files."""
from .localization import tr
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QFileDialog, QComboBox, QSlider, QSpinBox, QScrollArea, QLineEdit)
from .core import open_pdf


class DiffCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.images = None
        self.mode = 0
        self.amount = 50
        self.setMinimumSize(400, 250)

    def set_result(self, result):
        self.images = [QImage(array.data, array.shape[1], array.shape[0], array.strides[0], QImage.Format_RGB888).copy()
                       for array in (result.before, result.after, result.highlighted)]
        self.resize(self.images[0].size())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)
        if not self.images:
            return
        if self.mode == 0:
            painter.drawImage(0, 0, self.images[2])
            return
        painter.drawImage(0, 0, self.images[0])
        if self.mode == 1:
            split = round(self.images[0].width() * self.amount / 100)
            painter.setClipRect(split, 0, self.width() - split, self.height())
            painter.drawImage(0, 0, self.images[1])
            painter.setClipping(False)
            painter.setPen(QColor('#2452D6'))
            painter.drawLine(split, 0, split, self.height())
        else:
            painter.setOpacity(self.amount / 100)
            painter.drawImage(0, 0, self.images[1])


class DiffDialog(QDialog):
    def __init__(self, parent=None, before=None, after=None, before_password='', after_password=''):
        super().__init__(parent)
        self.paths = [Path(before) if before else None, Path(after) if after else None]
        self.counts = [0, 0]
        self.setWindowTitle(tr('어잉PDF · 두 문서 비교'))
        self.resize(1040, 820)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.file_buttons = []
        for index, name in enumerate((tr('원본 PDF 선택'), tr('수정본 PDF 선택'))):
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, i=index: self.choose(i))
            self.file_buttons.append(button)
            row.addWidget(button)
        self.page = QSpinBox()
        self.page.setRange(1, 1)
        self.page.valueChanged.connect(self.refresh)
        row.addWidget(QLabel(tr('페이지')))
        row.addWidget(self.page)
        self.mode = QComboBox()
        self.mode.addItems([tr('차이 강조'), tr('좌우 비교 슬라이더'), tr('겹쳐 보기')])
        row.addWidget(self.mode)
        close = QPushButton(tr('닫기'))
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)
        passwords = QHBoxLayout()
        self.password_fields = []
        for title, value in ((tr('원본 암호 (필요시)'), before_password), (tr('수정본 암호 (필요시)'), after_password)):
            field = QLineEdit(value)
            field.setEchoMode(QLineEdit.Password)
            field.setMaxLength(256)
            field.setPlaceholderText(title)
            field.setAccessibleName(title)
            field.editingFinished.connect(self.load_paths)
            passwords.addWidget(field)
            self.password_fields.append(field)
        layout.addLayout(passwords)
        self.status = QLabel(tr('같은 페이지 번호를 비교합니다. 빨강: 삭제 · 초록: 추가 · 보라: 같은 위치 변경'))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.canvas = DiffCanvas()
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.setAccessibleName(tr('원본과 수정본 비교 비율'))
        self.slider.valueChanged.connect(self.display_mode)
        self.mode.currentIndexChanged.connect(self.display_mode)
        layout.addWidget(self.slider)
        notice = QLabel(tr('시각 비교이며 의미 분석이나 자동 정렬은 하지 않습니다. 원본 파일은 수정하지 않습니다.'))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.display_mode()
        if all(self.paths):
            QTimer.singleShot(0, lambda: self.load_paths() if self.isVisible() else None)

    def clear_passwords(self):
        for field in self.password_fields:
            field.blockSignals(True)
            field.clear()
            field.blockSignals(False)

    def reject(self):
        self.clear_passwords()
        super().reject()

    def closeEvent(self, event):
        self.clear_passwords()
        super().closeEvent(event)

    def choose(self, index):
        name, _ = QFileDialog.getOpenFileName(self, tr('비교할 PDF 선택'), '', 'PDF (*.pdf)')
        if name:
            self.paths[index] = Path(name)
            self.load_paths()

    def load_paths(self):
        self.canvas.images = None
        self.canvas.update()
        self.counts = [0, 0]
        try:
            for index, path in enumerate(self.paths):
                if path:
                    with open_pdf(path, self.password_fields[index].text()) as doc:
                        self.counts[index] = len(doc)
                    self.file_buttons[index].setText(path.name[:45].replace('&', '&&'))
                    self.file_buttons[index].setToolTip(str(path))
            self.page.blockSignals(True)
            self.page.setRange(1, max(1, *self.counts))
            self.page.setSuffix(f' / {max(self.counts)}')
            self.page.blockSignals(False)
            self.refresh()
        except Exception as error:
            self.status.setText(tr('문서를 열지 못했습니다: {v0}', v0=error))

    def refresh(self):
        if not all(self.paths):
            return
        try:
            from .visual_diff import compare
            result = compare(*self.paths, page_index=self.page.value() - 1,
                             before_password=self.password_fields[0].text(), after_password=self.password_fields[1].text())
            self.canvas.set_result(result)
            missing = tr(' · 원본에 없는 페이지') if result.missing_before else tr(' · 수정본에 없는 페이지') if result.missing_after else ''
            self.status.setText(tr('차이 픽셀 {v0:,}개{v1} · 빨강: 삭제 · 초록: 추가 · 보라: 같은 위치 변경', v0=result.changed_pixels, v1=missing))
        except Exception as error:
            self.canvas.images = None
            self.canvas.update()
            self.status.setText(tr('비교하지 못했습니다: {v0}', v0=error))

    def display_mode(self):
        self.canvas.mode = self.mode.currentIndex()
        self.canvas.amount = self.slider.value()
        self.slider.setEnabled(self.canvas.mode != 0)
        self.canvas.update()


def show_diff(parent):
    from .license_ui import ensure_license
    if ensure_license(parent):
        DiffDialog(parent).exec()
