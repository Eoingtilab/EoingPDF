"""On-demand vault management with explicit import and delete actions."""
from .localization import tr
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QFileDialog, QInputDialog, QMessageBox)
from .seal_vault import SealVault, read_seal


class SealVaultDialog(QDialog):
    def __init__(self, parent=None, vault=None):
        super().__init__(parent)
        self.vault = vault or SealVault()
        self.selected_path = None
        self.setWindowTitle(tr('도장·서명 보관함'))
        self.resize(520, 540)
        layout = QVBoxLayout(self)
        notice = QLabel(tr('현재 Windows 계정으로 암호화해 보관합니다. 다른 계정·PC로 옮기면 열리지 않을 수 있습니다. 같은 계정으로 실행되는 프로그램에 대한 별도 잠금은 아닙니다.'))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.items = QListWidget()
        layout.addWidget(self.items)
        self.preview = QLabel(tr('도장을 선택해 주세요.'))
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(160)
        layout.addWidget(self.preview)
        self.items.currentItemChanged.connect(self.show_preview)
        row = QHBoxLayout()
        for text, callback in [(tr('추가'), self.add), (tr('삭제'), self.remove), (tr('이 도장 사용'), self.choose), (tr('닫기'), self.reject)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        self.items.clear()
        for path, name, valid in self.vault.entries():
            item = QListWidgetItem(name if valid else name + tr(' · 삭제 후 다시 추가하세요'))
            item.setData(Qt.UserRole, str(path))
            self.items.addItem(item)
        if self.items.count():
            self.items.setCurrentRow(0)

    def show_preview(self, item, previous=None):
        self.preview.clear()
        if item is None:
            self.preview.setText(tr('도장을 추가해 주세요.'))
            return
        try:
            _, stream = read_seal(item.data(Qt.UserRole))
            pixmap = QPixmap()
            if not pixmap.loadFromData(stream, 'PNG'):
                raise ValueError(tr('미리보기를 만들 수 없습니다.'))
            self.preview.setPixmap(pixmap.scaled(440, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except ValueError as error:
            self.preview.setText(str(error))

    def add(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('보관할 이미지 선택'), '', tr('이미지 (*.png *.jpg *.jpeg)'))
        if not path:
            return
        name, accepted = QInputDialog.getText(self, tr('도장 이름'), tr('보관함에서 표시할 이름'))
        if not accepted:
            return
        try:
            saved = self.vault.add(path, name)
            self.refresh()
            for index in range(self.items.count()):
                if self.items.item(index).data(Qt.UserRole) == str(saved):
                    self.items.setCurrentRow(index)
                    break
        except Exception as error:
            QMessageBox.warning(self, tr('도장 추가 실패'), str(error))

    def remove(self):
        item = self.items.currentItem()
        if item is None:
            return
        if QMessageBox.question(self, tr('도장 삭제'), tr('이 도장을 보관함에서 삭제할까요? 원본 이미지 파일은 유지합니다.'),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.vault.remove(item.data(Qt.UserRole))
            self.refresh()
        except Exception as error:
            QMessageBox.warning(self, tr('도장 삭제 실패'), str(error))

    def choose(self):
        item = self.items.currentItem()
        if item is None:
            return
        try:
            path = item.data(Qt.UserRole)
            read_seal(path)
            self.selected_path = path
            self.accept()
        except ValueError as error:
            QMessageBox.warning(self, tr('도장 선택 실패'), str(error))
