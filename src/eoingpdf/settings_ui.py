"""Shared settings entry point for shell, licensing and update services."""
import queue
import threading
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QTabWidget,
                               QWidget, QLabel, QPushButton, QComboBox)
from .sdk_theme import apply_style
from .updates import current_version, latest_backup
from .localization import tr


class SettingsDialog(QDialog):
    def __init__(self, parent=None, shell_settings=None):
        super().__init__(parent)
        self._backup_results = queue.Queue()
        self._backup_pending = False
        self._backup = None
        self.setWindowTitle(tr('어잉PDF · 설정'))
        self.resize(620, 460)
        apply_style(self, '''
            QDialog, QWidget {background:#f6f8fc;color:#193455;}
            QLabel {background:transparent;color:#193455;}
            QPushButton {background:white;color:#193455;border:1px solid #dbe5f5;
                         border-radius:8px;min-height:40px;padding:0 16px;}
            QPushButton:disabled {color:#8b9bb1;}
            QTabWidget::pane {border:1px solid #dbe5f5;border-radius:12px;}
            QTabBar::tab {padding:12px 20px;background:#edf2f9;color:#193455;}
            QTabBar::tab:selected {background:white;color:#4f6bff;}
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        general = self.page(tr('일반'))
        self.description(general, tr('화면 테마'))
        self.theme_choice = QComboBox()
        for title, mode in [(tr('시스템 설정 따름'), 'system'), (tr('밝게'), 'light'), (tr('어둡게'), 'dark')]:
            self.theme_choice.addItem(tr(title), mode)
        controller = getattr(QApplication.instance(), 'eoing_theme', None)
        self.theme_choice.setCurrentIndex(self.theme_choice.findData(controller.preference if controller else 'system'))
        self.theme_choice.setAccessibleName(tr('화면 테마'))
        self.theme_choice.setEnabled(controller is not None)
        if controller:
            self.theme_choice.currentIndexChanged.connect(
                lambda index: controller.set_preference(self.theme_choice.itemData(index)))
        general.addWidget(self.theme_choice)
        self.description(general, tr('탐색기에서 문서를 선택해 빠르게 처리하고, PDF를 어잉PDF로 열 수 있습니다.'))
        self.shell = QPushButton(tr('우클릭 메뉴·기본 PDF 앱 설정'))
        self.shell.setEnabled(shell_settings is not None)
        if shell_settings:
            self.shell.clicked.connect(shell_settings)
        general.addWidget(self.shell)
        self.shell_status = QLabel()
        self.shell_status.setWordWrap(True)
        general.addWidget(self.shell_status)
        self.description(general, tr('기본 PDF 앱은 Windows 설정에서 직접 선택합니다. 앱은 Windows 시작 시 상주하지 않습니다.'))
        general.addStretch()
        license_page = self.page(tr('라이선스'))
        self.description(license_page, tr('최초 활성화에는 인터넷이 필요합니다. 활성화한 PC에서는 오프라인으로 문서를 처리할 수 있습니다.'))
        self.license_button = QPushButton(tr('라이선스 활성화·비활성화'))
        self.license_button.clicked.connect(self.manage_license)
        license_page.addWidget(self.license_button)
        self.description(license_page, tr('다른 키로 바꾸려면 현재 라이선스를 먼저 비활성화하세요. 비활성화와 재활성화에는 인터넷 연결이 필요합니다.'))
        license_page.addStretch()
        update_page = self.page(tr('업데이트'))
        self.description(update_page, tr('현재 버전: {version}', version=current_version()))
        self.description(update_page, tr('실행 시 새 버전을 확인합니다. 저장하지 않은 문서나 진행 중인 작업이 있으면 설치를 기다립니다.'))
        self.update_status = QLabel()
        self.update_status.setWordWrap(True)
        update_page.addWidget(self.update_status)
        self.rollback_status = QLabel()
        self.rollback_status.setWordWrap(True)
        update_page.addWidget(self.rollback_status)
        self.rollback_button = QPushButton(tr('이전 버전으로 복원'))
        self.rollback_button.clicked.connect(self.show_rollback_help)
        self.rollback_button.setEnabled(False)
        self.rollback_status.setText(tr('복원 가능한 백업을 확인합니다.'))
        update_page.addWidget(self.rollback_button)
        self.check_button = QPushButton(tr('지금 확인'))
        self.check_button.clicked.connect(self.check_updates)
        update_page.addWidget(self.check_button)
        update_page.addStretch()
        close = QPushButton(tr('닫기'))
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.refresh()

    def page(self, title):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        self.tabs.addTab(widget, tr(title))
        return layout

    @staticmethod
    def description(layout, text):
        label = QLabel(tr(text))
        label.setWordWrap(True)
        layout.addWidget(label)

    def manage_license(self):
        from .license_ui import settings
        settings(self)

    def check_updates(self):
        updater = getattr(QApplication.instance(), 'updater', None)
        if updater is not None:
            updater.check()
        self.request_backup_check()
        self.refresh()

    def request_backup_check(self):
        if self._backup_pending:
            return
        self._backup_pending = True
        self.rollback_button.setEnabled(False)
        self.rollback_status.setText(tr('백업 무결성을 확인하고 있습니다.'))
        results = self._backup_results
        # The background job owns no Qt object and can finish safely after close.
        def work():
            try:
                results.put((latest_backup(), None))
            except Exception as error:
                results.put((None, str(error)))
        threading.Thread(target=work, daemon=True).start()

    def show_rollback_help(self):
        from PySide6.QtWidgets import QMessageBox
        backup = self._backup
        if backup is None or self._backup_pending:
            QMessageBox.information(self, tr('이전 버전 복원'), tr('검증된 업데이트 백업이 없습니다.'))
            return
        folder, version = backup
        for widget in QApplication.topLevelWidgets():
            worker = getattr(widget, 'worker', None)
            has_ink = getattr(widget, 'has_ink', None)
            if (getattr(widget, 'dirty', False) or worker is not None and worker.isRunning()
                    or callable(has_ink) and has_ink()):
                QMessageBox.information(self, tr('이전 버전 복원'), tr('진행 중인 작업을 마치고 변경 내용을 저장한 뒤 다시 시도해 주세요.'))
                return
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle(tr('이전 버전 복원'))
        confirmation.setText(tr('{v0} 버전으로 복원하고 프로그램을 다시 시작할까요?', v0=version))
        restore = confirmation.addButton(tr('복원 후 다시 시작'), QMessageBox.AcceptRole)
        cancel = confirmation.addButton(tr('취소'), QMessageBox.RejectRole)
        confirmation.setDefaultButton(cancel)
        confirmation.exec()
        if confirmation.clickedButton() is not restore:
            return
        try:
            from .update_helper import launch
            report = launch(folder)
            self.rollback_status.setText(tr('종료 후 복원을 시작합니다. 결과 기록: {v0}', v0=report))
            self.timer.stop()
            QApplication.instance().quit()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, tr('복원 시작 실패'), str(error))

    def refresh(self):
        from .shell import registration_status
        try:
            shell = registration_status()
            if shell['ready']:
                self.shell_status.setText(tr('우클릭 메뉴와 PDF 열기 연결이 현재 설치본으로 등록되어 있습니다.'))
            elif shell['owner'] != '없음':
                self.shell_status.setText(tr('다른 설치본이 PDF 열기 연결을 사용 중입니다. 이 설치본으로 다시 등록하려면 위 버튼을 누르세요.'))
            else:
                self.shell_status.setText(tr('우클릭 메뉴가 아직 등록되지 않았습니다. 위 버튼에서 등록할 수 있습니다.'))
        except Exception:
            self.shell_status.setText(tr('우클릭 메뉴 등록 상태를 확인하지 못했습니다.'))
        try:
            backup, error = self._backup_results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._backup_pending = False
            self._backup = backup
            self.rollback_status.setText(tr('백업을 확인하지 못했습니다: ') + error if error else
                                         tr('복원 가능한 이전 버전: {v0}', v0=backup[1]) if backup else tr('복원 가능한 이전 버전이 없습니다.'))
            self.rollback_button.setEnabled(backup is not None and error is None)
        updater = getattr(QApplication.instance(), 'updater', None)
        if updater is None:
            self.update_status.setText(tr('이 실행 환경에서는 자동 업데이트 서비스가 시작되지 않았습니다.'))
            self.check_button.setEnabled(False)
            return
        self.update_status.setText(tr('설치 파일이 준비되었습니다. 설정 창을 닫고 진행 중인 작업을 마치면 적용됩니다.'
                                   if updater.pending else updater.message))
        self.check_button.setEnabled(not updater.running and not updater.pending)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.request_backup_check()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
