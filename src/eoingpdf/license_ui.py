"""Responsive activation, deactivation and reactivation settings."""
from .sdk_theme import apply_style
from .localization import tr
from PySide6.QtCore import QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from .licensing import store, LicenseError, STORE_URL, ITEM_ID


class LicenseWorker(QThread):
    completed = Signal(bool, str)

    def __init__(self, action, key):
        super().__init__()
        self.action, self.key = action, key

    def run(self):
        try:
            active = store().perform(self.action, self.key)
            self.completed.emit(active, tr('라이선스가 활성화되었습니다.') if active else tr('이 PC의 활성화를 해제했습니다. 같은 키로 다시 활성화할 수 있습니다.'))
        except LicenseError as error:
            self.completed.emit(False, str(error))
        except Exception:
            self.completed.emit(False, tr('라이선스 정보를 저장하지 못했습니다. PC 저장 권한을 확인해 주세요.'))


class LicenseDialog(QDialog):
    def __init__(self, parent=None, required=False):
        super().__init__(parent)
        self.required = required
        self.worker = None
        self.setWindowTitle(tr('어잉PDF · 라이선스 설정'))
        self.setMinimumWidth(490)
        apply_style(self, 'QDialog {background:#f7f9fc;} QLabel {color:#263246;} QLineEdit {background:white;color:#263246;padding:10px;border:1px solid #b9cbed;border-radius:6px;} QPushButton {background:white;color:#263246;padding:9px 14px;border:1px solid #dae2f0;border-radius:6px;min-height:22px;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel(tr('라이선스 활성화'))
        apply_style(title, 'font-size:22px;font-weight:600;')
        layout.addWidget(title)
        explanation = QLabel(tr('무료 이용도 라이선스 등록이 필요합니다.\napp.nal.la에서 발급받은 어잉PDF 키를 입력해 주세요.'))
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.key = QLineEdit(store().data.get('key', ''))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText(tr('라이선스 키'))
        self.key.setAccessibleName(tr('라이선스 키'))
        layout.addWidget(self.key)
        self.status = QLabel(tr('활성화 상태입니다.' if store().valid_session() else '라이선스 확인이 필요합니다.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.activate = QPushButton(tr('활성화 / 재활성화'))
        self.check = QPushButton(tr('상태 확인'))
        self.deactivate = QPushButton(tr('비활성화'))
        for button, action in [(self.activate, 'activate_license'), (self.check, 'check_license'), (self.deactivate, 'deactivate_license')]:
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, a=action: self.start(a))
            row.addWidget(button)
        layout.addLayout(row)
        notice = QLabel(tr('최초 활성화 후에는 인터넷 없이도 사용할 수 있습니다.\n활성화·상태 확인·비활성화·업데이트에는 인터넷이 필요합니다.\n인증 시 키와 임의의 PC 식별자만 전송하며 문서는 전송하지 않습니다.'))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        bottom = QHBoxLayout()
        issue = QPushButton(tr('라이선스 발급 페이지'))
        issue.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f'{STORE_URL}?p={ITEM_ID}')))
        bottom.addWidget(issue)
        self.finish = QPushButton(tr('계속' if required else '닫기'))
        self.finish.clicked.connect(self.finish_dialog)
        bottom.addWidget(self.finish)
        layout.addLayout(bottom)
        if required and store().valid_session():
            QTimer.singleShot(0, self.accept)
        elif required and store().data.get('key'):
            QTimer.singleShot(0, lambda: self.start('check_license') if self.isVisible() else None)

    def start(self, action):
        if self.worker and self.worker.isRunning():
            return
        self.status.setText(tr('라이선스 서버에 확인하고 있습니다…'))
        for widget in (self.key, self.activate, self.check, self.deactivate, self.finish):
            widget.setEnabled(False)
        self.worker = LicenseWorker(action, self.key.text())
        self.worker.completed.connect(self.completed)
        self.worker.finished.connect(self.idle)
        self.worker.start()

    def completed(self, active, message):
        self.status.setText(tr(message))

    def idle(self):
        for widget in (self.key, self.activate, self.check, self.deactivate, self.finish):
            widget.setEnabled(True)
        if self.required and store().valid_session():
            self.accept()

    def finish_dialog(self):
        if not self.required or store().valid_session():
            self.accept()
        else:
            self.status.setText(tr('라이선스를 활성화한 뒤 계속할 수 있습니다.'))

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            event.accept()


def ensure_license(parent=None):
    if store().valid_session():
        return True
    dialog = LicenseDialog(parent, required=True)
    return dialog.exec() == QDialog.Accepted and store().valid_session()


def settings(parent=None):
    LicenseDialog(parent).exec()


def main():
    import sys
    from .app import STYLE, ROOT
    from .localization import install_language
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase, QFont, QIcon
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    from .sdk_theme import install_theme
    install_theme(app)
    from .sdk_theme import apply_style
    apply_style(app, STYLE)
    app.setWindowIcon(QIcon(str(ROOT / 'assets/app_icon.png')))
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    install_language(app)
    dialog = LicenseDialog(required=True)
    return 0 if dialog.exec() == QDialog.Accepted and store().valid_session() else 1
