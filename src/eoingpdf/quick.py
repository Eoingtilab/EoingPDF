"""A small, nonresident progress window for Explorer actions."""
import argparse
from pathlib import Path
import sys
from PySide6.QtCore import QThread, Signal, QTimer, QUrl, Qt
from PySide6.QtGui import QFontDatabase, QFont, QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QPlainTextEdit
from .jobs import execute
from .convert import ROOT


class QuickWorker(QThread):
    progress = Signal(int, str)
    result = Signal(dict)

    def __init__(self, action, files, folder=None):
        super().__init__()
        self.action, self.files, self.folder = action, files, folder

    def run(self):
        try:
            result = execute(self.action, self.files, self.folder, self.progress.emit, self.isInterruptionRequested)
        except Exception as error:
            result = {'outputs': [], 'errors': [str(error)], 'cancelled': self.isInterruptionRequested()}
        self.result.emit(result)


class QuickWindow(QWidget):
    def __init__(self, action, files, folder=None):
        super().__init__()
        self.setWindowTitle('어잉PDF · 빠른 작업')
        self.setMinimumWidth(450)
        self.resize(490, 220)
        self.outputs = []
        self.pending_start = True
        self.worker = QuickWorker(action, files, folder)
        self.setStyleSheet("QWidget {background:#f8faff; color:#26364d; font-family:Pretendard; font-size:14px;} QPushButton {background:white;border:1px solid #dae2f0;border-radius:8px;padding:10px 16px;} QProgressBar {border:0;background:#e3eafa;border-radius:3px;max-height:6px;} QProgressBar::chunk{background:#5176ec;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 24, 25, 24)
        layout.setSpacing(14)
        title = QLabel({'merge': '하나의 PDF로 합치고 있어요', 'convert': 'PDF로 바꾸고 있어요', 'summary': '핵심문장을 정리하고 있어요'}[action])
        title.setStyleSheet('font-size:20px;font-weight:600;')
        layout.addWidget(title)
        self.title = title
        self.status = QLabel(f'{len(files)}개 파일 · 원본은 그대로 보관합니다')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.hide()
        layout.addWidget(self.details)
        row = QHBoxLayout()
        row.addStretch()
        self.open_button = QPushButton('결과 폴더 열기')
        self.open_button.hide()
        self.open_button.clicked.connect(self.open_folder)
        row.addWidget(self.open_button)
        self.cancel_button = QPushButton('취소')
        self.cancel_button.clicked.connect(self.cancel_or_close)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.completed)
        self.worker.finished.connect(lambda: self.cancel_button.setText('닫기'))
        QTimer.singleShot(0, self.start_worker)

    def start_worker(self):
        if self.pending_start:
            self.pending_start = False
            self.worker.start()

    def on_progress(self, value, message):
        self.progress.setValue(value)
        self.status.setText(message)

    def completed(self, result):
        self.outputs = result['outputs']
        errors = result['errors']
        self.title.setText('작업을 취소했어요' if result['cancelled'] else '결과를 확인해 주세요' if errors else '완료했어요!')
        self.status.setText(f'완료 {len(self.outputs)}개 · 실패 {len(errors)}개 · 원본 보존')
        self.progress.setValue(100 if not errors and not result['cancelled'] else 0)
        self.open_button.setVisible(bool(self.outputs))
        self.details.setPlainText('\n'.join(self.outputs + errors))
        self.details.show()
        self.resize(490, 340)

    def open_folder(self):
        if self.outputs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.outputs[0]).parent)))

    def cancel_or_close(self):
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.status.setText('현재 단계가 끝나면 취소합니다…')
        else:
            self.close()

    def closeEvent(self, event):
        self.pending_start = False
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.status.setText('취소 중입니다. 잠시 기다려 주세요.')
            event.ignore()
        else:
            event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', choices=['merge', 'convert', 'summary'], required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--folder')
    parser.add_argument('files', nargs='*')
    args = parser.parse_args()
    paths = args.files
    if args.manifest:
        manifest = Path(args.manifest).resolve()
        paths += manifest.read_text(encoding='utf-8-sig').splitlines()
        # Only delete manifests created in our own queue.
        import os
        queue = (Path(os.environ.get('LOCALAPPDATA', '')) / 'EoingPDF/queue').resolve()
        if manifest.parent == queue and manifest.suffix == '.files':
            manifest.unlink()
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(QIcon(str(ROOT / 'assets/app_icon.png')))
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    window = QuickWindow(args.quick, paths, args.folder)
    window.show()
    sys.exit(app.exec())
