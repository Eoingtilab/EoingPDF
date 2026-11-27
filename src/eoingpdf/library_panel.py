"""Stirling-style PDF Library sidebar for managing multiple open/working files."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from .action_icons import set_action_icon
from .convert import SUPPORTED
from .localization import tr
from .sdk_theme import apply_style


def _safe_resolve(raw: str | Path) -> Path:
    try:
        return Path(raw).resolve()
    except OSError:
        return Path(os.path.abspath(str(raw)))


class LibraryPanel(QWidget):
    """Manage open PDFs and documents for quick switching or batch operations."""

    open_requested = Signal(str)
    batch_merge_requested = Signal(list)
    batch_convert_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('libraryPanel')
        self.paths: list[Path] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr('문서 라이브러리')), 1)
        add_btn = QPushButton(tr('+ 추가'))
        add_btn.setAutoDefault(False)
        set_action_icon(add_btn, 'open')
        add_btn.clicked.connect(self.choose_files)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self.list = QListWidget()
        self.list.setObjectName('libraryList')
        self.list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list, 1)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        self.merge_btn = QPushButton(tr('체크 합치기'))
        set_action_icon(self.merge_btn, 'pages')
        self.merge_btn.clicked.connect(lambda: self.batch_merge_requested.emit(self.checked_or_all()))
        actions.addWidget(self.merge_btn)

        self.convert_btn = QPushButton(tr('PDF 변환'))
        set_action_icon(self.convert_btn, 'export')
        self.convert_btn.clicked.connect(lambda: self.batch_convert_requested.emit(self.checked_or_all()))
        actions.addWidget(self.convert_btn)
        layout.addLayout(actions)

        remove_row = QHBoxLayout()
        remove_btn = QPushButton(tr('선택 제거'))
        set_action_icon(remove_btn, 'delete')
        remove_btn.clicked.connect(self.remove_selected)
        remove_row.addWidget(remove_btn)
        clear_btn = QPushButton(tr('비우기'))
        set_action_icon(clear_btn, 'clear')
        clear_btn.clicked.connect(self.clear)
        remove_row.addWidget(clear_btn)
        layout.addLayout(remove_row)

        apply_style(self, 'QWidget#libraryPanel {background:#eef2f8;} QListWidget {background:white;border:1px solid #dae2f0;border-radius:6px;} QPushButton {padding:5px 8px;}')
        self.refresh_buttons()

    def add_paths(self, raw_paths: list[str | Path]) -> list[Path]:
        added = []
        known = {str(_safe_resolve(p)).casefold() for p in self.paths}
        for raw in raw_paths:
            try:
                p = _safe_resolve(raw)
            except OSError:
                continue
            if not p.is_file() or p.suffix.lower() not in SUPPORTED:
                continue
            key = str(p).casefold()
            if key in known:
                continue
            known.add(key)
            self.paths.append(p)
            added.append(p)
            size_mb = p.stat().st_size / 1048576
            item = QListWidgetItem(f'{p.name}\n{size_mb:.2f} MB')
            item.setData(Qt.UserRole, str(p))
            item.setToolTip(str(p))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if p.suffix.lower() == '.pdf' else Qt.Unchecked)
            self.list.addItem(item)
        self.refresh_buttons()
        return added

    def choose_files(self):
        ext_filter = tr('지원 문서') + ' (' + ' '.join('*' + ext for ext in sorted(SUPPORTED)) + ')'
        paths, _ = QFileDialog.getOpenFileNames(self, tr('작업실에 파일 추가'), '', ext_filter)
        added = self.add_paths(paths)
        first_pdf = next((p for p in added if p.suffix.lower() == '.pdf'), None)
        if first_pdf is not None:
            self.open_requested.emit(str(first_pdf))

    def checked_or_all(self) -> list[str]:
        checked = [
            self.list.item(i).data(Qt.UserRole)
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.Checked
        ]
        if checked:
            return checked
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def _on_item_clicked(self, item: QListWidgetItem):
        path = Path(item.data(Qt.UserRole))
        if path.suffix.lower() == '.pdf':
            self.open_requested.emit(str(path))

    def remove_selected(self):
        row = self.list.currentRow()
        if row >= 0:
            item = self.list.takeItem(row)
            target = _safe_resolve(item.data(Qt.UserRole))
            self.paths = [p for p in self.paths if _safe_resolve(p) != target]
            self.refresh_buttons()

    def clear(self):
        self.paths.clear()
        self.list.clear()
        self.refresh_buttons()

    def highlight_active(self, active_path: Path | None):
        if active_path is None:
            return
        active_key = str(_safe_resolve(active_path)).casefold()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if str(_safe_resolve(item.data(Qt.UserRole))).casefold() == active_key:
                self.list.setCurrentRow(i)
                break

    def refresh_buttons(self):
        has_items = self.list.count() > 0
        self.merge_btn.setEnabled(has_items)
        self.convert_btn.setEnabled(has_items)
