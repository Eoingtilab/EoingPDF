"""Window-scoped, nonresident file collection and ordered batch merge."""
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QRect, QPoint
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QAbstractItemView, QFileDialog,
                               QProgressBar, QPlainTextEdit)

from .convert import SUPPORTED
from .localization import tr
from .quick import QuickWorker
from .sdk_theme import apply_style


def snapped_position(frame: QRect, available: QRect, distance=24):
    """Clamp to a screen's work area and magnetize nearby edges in logical pixels."""
    right = available.x() + max(0, available.width() - frame.width())
    bottom = available.y() + max(0, available.height() - frame.height())
    x = max(available.x(), min(frame.x(), right))
    y = max(available.y(), min(frame.y(), bottom))
    if x - available.x() <= distance:
        x = available.x()
    elif right - x <= distance:
        x = right
    if y - available.y() <= distance:
        y = available.y()
    elif bottom - y <= distance:
        y = bottom
    return QPoint(x, y)


class FileList(QListWidget):
    def __init__(self, dock):
        super().__init__(dock)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAccessibleName(tr('병합할 파일 목록 · 끌어서 순서 변경'))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.parent().dragEnterEvent(event)
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            self.parent().dragEnterEvent(event)
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.parent().dropEvent(event)
        else:
            super().dropEvent(event)


class StagingDock(QWidget):
    MAX_FILES = 1000

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(tr('어잉PDF · 파일 모으기'))
        self.setAcceptDrops(True)
        self.resize(340, 410)
        self.setMinimumSize(300, 330)
        self.worker = None
        self.folder = None
        self.output = None
        self.dirty = False
        self.close_pending = False
        self.positioned = False
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.timeout.connect(self.snap_to_edge)
        apply_style(self, '''QWidget {font-family:Pretendard;font-size:13px;color:#26364d;}
            StagingDock {background:#f8faff;}
            QListWidget,QPlainTextEdit {background:white;border:1px solid #dae2f0;border-radius:6px;}
            QPushButton {background:white;border:1px solid #dae2f0;border-radius:6px;padding:6px;}
            QPushButton:disabled {color:#8994a6;}''')
        layout = QVBoxLayout(self)
        hint = QLabel(tr('여러 폴더의 파일을 여기에 모아주세요.'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.files = FileList(self)
        layout.addWidget(self.files, 1)
        row = QHBoxLayout()
        self.add_button = QPushButton(tr('파일 추가'))
        self.add_button.clicked.connect(self.choose_files)
        self.remove_button = QPushButton(tr('선택 제거'))
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton(tr('비우기'))
        self.clear_button.clicked.connect(self.clear_files)
        for button in (self.add_button, self.remove_button, self.clear_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.delete_shortcut = QShortcut(QKeySequence.Delete, self.files)
        self.delete_shortcut.activated.connect(self.remove_selected)
        self.folder_button = QPushButton(tr('저장 위치: 첫 파일과 같은 폴더'))
        self.folder_button.clicked.connect(self.choose_folder)
        layout.addWidget(self.folder_button)
        self.status = QLabel(tr('파일 0개 · 원본 보존'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        layout.addWidget(self.progress)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(90)
        self.details.hide()
        layout.addWidget(self.details)
        row = QHBoxLayout()
        self.merge_button = QPushButton(tr('하나의 PDF로 합치기'))
        self.merge_button.clicked.connect(self.merge)
        self.cancel_button = QPushButton(tr('취소'))
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.hide()
        self.open_button = QPushButton(tr('결과 폴더 열기'))
        self.open_button.clicked.connect(self.open_result)
        self.open_button.hide()
        for button in (self.merge_button, self.cancel_button, self.open_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.refresh()

    def paths(self):
        return [self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())]

    def refresh(self):
        self.dirty = bool(self.files.count())
        self.merge_button.setEnabled(self.dirty and self.worker is None)
        self.status.setText(tr('파일 {count}개 · 원본 보존', count=self.files.count()))

    def add_files(self, paths):
        if self.worker is not None:
            return
        known = {os.path.normcase(path) for path in self.paths()}
        rejected = 0
        for raw in paths:
            try:
                path = Path(raw).resolve(strict=True)
                if not path.is_file() or path.suffix.lower() not in SUPPORTED:
                    raise ValueError()
                key = os.path.normcase(str(path))
                if key in known:
                    continue
                if self.files.count() >= self.MAX_FILES:
                    raise ValueError()
                item = QListWidgetItem(path.name)
                item.setToolTip(str(path))
                item.setData(Qt.UserRole, str(path))
                self.files.addItem(item)
                known.add(key)
            except (OSError, ValueError, RuntimeError):
                rejected += 1
        self.refresh()
        if rejected:
            self.status.setText(tr('파일 {count}개 · 제외 {rejected}개 (폴더·미지원·누락·1000개 초과)',
                                   count=self.files.count(), rejected=rejected))

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('파일 추가'), '',
                                              tr('지원 문서') + ' (' + ' '.join('*' + ext for ext in sorted(SUPPORTED)) + ')')
        self.add_files(paths)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr('저장 폴더 선택'), self.folder or '')
        if folder:
            self.folder = folder
            self.folder_button.setText(tr('저장 위치: {name}', name=Path(folder).name or folder))
            self.folder_button.setToolTip(folder)

    def remove_selected(self):
        if self.worker is None:
            for item in self.files.selectedItems():
                self.files.takeItem(self.files.row(item))
            self.refresh()

    def clear_files(self):
        if self.worker is None:
            self.files.clear()
            self.refresh()

    def dragEnterEvent(self, event):
        if self.worker is None and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.worker is not None:
            event.ignore()
            return
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def set_busy(self, busy):
        for widget in (self.files, self.add_button, self.remove_button, self.clear_button, self.folder_button):
            widget.setEnabled(not busy)
        self.merge_button.setEnabled(not busy and bool(self.files.count()))
        self.cancel_button.setVisible(busy)

    def merge(self):
        if self.worker is not None or not self.files.count():
            return
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        self.output = None
        self.open_button.hide()
        self.details.hide()
        self.progress.setValue(0)
        self.worker = QuickWorker('merge', self.paths(), self.folder)
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.completed)
        self.worker.finished.connect(self.finished)
        self.set_busy(True)
        self.worker.start()

    def on_progress(self, value, message):
        self.progress.setValue(value)
        self.status.setText(message)

    def completed(self, result):
        outputs, errors = result['outputs'], result['errors']
        self.output = Path(outputs[0]) if outputs else None
        self.open_button.setVisible(bool(outputs))
        self.status.setText(tr('작업을 취소했어요') if result['cancelled'] else
                            tr('완료 {done}개 · 실패 {failed}개 · 원본 보존', done=len(outputs), failed=len(errors)))
        self.details.setPlainText('\n'.join(outputs + errors))
        self.details.setVisible(bool(outputs or errors))
        self.progress.setValue(100 if outputs else 0)

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)
        if self.close_pending:
            self.close()

    def cancel(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.status.setText(tr('현재 단계가 끝나면 취소합니다…'))

    def open_result(self):
        if self.output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output.parent)))

    def showEvent(self, event):
        super().showEvent(event)
        if not self.positioned:
            screen = self.screen().availableGeometry()
            self.move(screen.right() - self.frameGeometry().width() - 15,
                      screen.bottom() - self.frameGeometry().height() - 15)
            self.positioned = True

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'snap_timer') and self.isVisible():
            self.snap_timer.start(100)

    def snap_to_edge(self):
        if not self.isVisible():
            return
        if QGuiApplication.mouseButtons() != Qt.NoButton:
            self.snap_timer.start(100)
            return
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or self.screen()
        position = snapped_position(self.frameGeometry(), screen.availableGeometry())
        if position != self.pos():
            self.move(position)

    def closeEvent(self, event):
        if self.worker is not None:
            self.close_pending = True
            self.cancel()
            event.ignore()
        else:
            self.snap_timer.stop()
            self.close_pending = False
            self.clear_files()
            event.accept()


def show_dock(parent):
    from .license_ui import ensure_license
    if not ensure_license(parent):
        return
    dock = getattr(parent, 'staging_dock', None)
    if dock is None:
        dock = parent.staging_dock = StagingDock(parent)
    dock.show()
    dock.raise_()
    dock.activateWindow()
