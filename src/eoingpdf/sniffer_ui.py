"""Event-scoped subprocess keeps MuPDF inspection separate from viewer rendering."""
import json
import sys
import time
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QMenu
from shiboken6 import isValid
from .localization import tr


class MicroSniffer(QObject):
    result = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None

    def start(self, path, trigger='open'):
        if trigger not in {'open', 'print'}:
            raise ValueError('Unsupported diagnostic trigger')
        self.stop()
        process = QProcess(self)
        self.process = process
        started = time.perf_counter()
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.timeout.connect(process.kill)
        root = Path(__file__).resolve().parents[2]
        arguments = ([] if getattr(sys, 'frozen', False) else [str(root / 'main.py')])
        arguments += ['--sniff-child', str(path), trigger]
        completed = False

        def complete(*_):
            nonlocal completed
            if completed or not isValid(self) or not isValid(process) or not isValid(timer):
                return
            completed = True
            timer.stop()
            if self.process is not process:
                process.deleteLater()
                return
            self.process = None
            raw = bytes(process.readAllStandardOutput())
            try:
                if len(raw) > 65536 or process.exitCode() != 0:
                    raise ValueError('Invalid diagnostics')
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError('Invalid diagnostics')
                result['total_ms'] = round((time.perf_counter() - started) * 1000, 3)
                self.result.emit(result)
            except (ValueError, UnicodeError):
                self.result.emit({'diagnostics': [], 'error': tr('자동 진단을 건너뛰었습니다.')})
            process.deleteLater()

        def failed(*_):
            if isValid(process) and process.state() == QProcess.NotRunning:
                complete()

        process.finished.connect(complete)
        process.errorOccurred.connect(failed)
        process.start(sys.executable, arguments)
        timer.start(3000)

    def stop(self):
        if self.process is not None:
            process, self.process = self.process, None
            if not isValid(process):
                return
            process.finished.disconnect()
            process.errorOccurred.disconnect()
            process.kill()
            if process.waitForFinished(100) or process.state() == QProcess.NotRunning:
                process.deleteLater()
            else:
                process.finished.connect(process.deleteLater)


class DiagnosticChips(QWidget):
    action = Signal(str)
    supported_actions = frozenset({'metadata', 'deskew', 'flatten', 'presentation',
        'searchable', 'table', 'four_up', 'decrypt', 'repair', 'stitch', 'rename', 'safe_submission', 'print_light'})

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.suggested_name = ''
        self.more_button = None
        self.hide()

    def display(self, report):
        name = report.get('suggested_name', '')
        self.suggested_name = name if isinstance(name, str) else ''
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().setEnabled(False)
                item.widget().hide()
                item.widget().deleteLater()
        self.more_button = None
        findings = report.get('diagnostics', [])
        if not isinstance(findings, list):
            findings = []
        findings = [finding for finding in findings if isinstance(finding, dict)
                    and all(isinstance(finding.get(key), str) for key in ('action', 'title', 'code'))]
        # Actions with actual destinations are interactive; other findings remain explanatory.
        for finding in findings[:3]:
            if finding['action'] in self.supported_actions:
                widget = QPushButton(tr(finding['title']))
                widget.setAutoDefault(False)
                widget.clicked.connect(lambda checked=False, action=finding['action']: self.action.emit(action))
            else:
                widget = QLabel(tr(finding['title']))
            widget.setToolTip(finding['code'])
            self.row.addWidget(widget)
        if len(findings) > 3:
            self.more_button = QPushButton(tr('추천 더 보기 · {v0}', v0=len(findings) - 3))
            self.more_button.setAutoDefault(False)
            menu = QMenu(self.more_button)
            menu.setToolTipsVisible(True)
            for finding in findings[3:]:
                action = menu.addAction(tr(finding['title']))
                action.setToolTip(finding['code'])
                action.setEnabled(finding['action'] in self.supported_actions)
                action.triggered.connect(lambda checked=False, key=finding['action']: self.action.emit(key))
            self.more_button.setMenu(menu)
            self.row.addWidget(self.more_button)
        self.row.addStretch()
        self.setVisible(bool(findings))
