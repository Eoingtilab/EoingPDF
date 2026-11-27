"""Visual Multi-Tool page workspace (reorder, rotate, duplicate, delete, insert, extract)."""
from __future__ import annotations

from pathlib import Path

import pymupdf as pdf
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QListView,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from .action_icons import set_action_icon
from .core import open_pdf
from .localization import tr
from .sdk_theme import apply_style


class _PageGridList(QListWidget):
    reordered = Signal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()


class MultiToolWidget(QWidget):
    """Stirling-style visual page editor board inside the main workbench."""

    apply_to_viewer = Signal(str)
    close_requested = Signal()

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.entries: list[dict] = []
        self.setObjectName('multiToolBoard')
        self.setMinimumSize(0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        bar_top = QHBoxLayout()
        bar_top.setSpacing(6)
        title = QLabel(tr('페이지 멀티툴 · 끌어서 순서 변경 · 다중 선택 후 일괄 편집'))
        title.setStyleSheet('font-weight:700;')
        title.setWordWrap(True)
        bar_top.addWidget(title, 1)

        def mk_btn(label, cb, icon_name=''):
            button = QPushButton(tr(label))
            button.setAutoDefault(False)
            button.setMinimumWidth(0)
            if icon_name:
                set_action_icon(button, icon_name)
            button.clicked.connect(cb)
            return button

        self.apply_btn = mk_btn('뷰어에 적용', self.commit_to_viewer, 'save')
        self.apply_btn.setObjectName('primary')
        bar_top.addWidget(self.apply_btn)
        bar_top.addWidget(mk_btn('뷰어로 돌아가기', self.close_requested.emit, 'close'))
        layout.addLayout(bar_top)

        bar_actions = QHBoxLayout()
        bar_actions.setSpacing(4)
        for label, cb, icon_name in (
            ('↺ 좌회전', lambda: self.rotate_selected(270), 'undo'),
            ('↻ 우회전', lambda: self.rotate_selected(90), 'redo'),
            ('복제', self.duplicate_selected, 'copy'),
            ('빈 페이지 +', self.insert_blank_after, 'pages'),
            ('PDF 끼워넣기', self.insert_pdf_file, 'open'),
            ('선택 삭제', self.delete_selected, 'delete'),
            ('선택 추출', self.extract_selected, 'export'),
        ):
            bar_actions.addWidget(mk_btn(label, cb, icon_name))
        bar_actions.addStretch(1)
        layout.addLayout(bar_actions)

        self.grid = _PageGridList()
        self.grid.setMinimumSize(0, 0)
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Snap)
        self.grid.setDragDropMode(QAbstractItemView.InternalMove)
        self.grid.setDefaultDropAction(Qt.MoveAction)
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grid.setIconSize(QSize(132, 174))
        self.grid.setGridSize(QSize(164, 224))
        self.grid.setSpacing(10)
        self.grid.reordered.connect(self._sync_order_from_grid)
        layout.addWidget(self.grid, 1)

        self.info_label = QLabel()
        layout.addWidget(self.info_label)
        apply_style(self, 'QWidget#multiToolBoard {background:#eef2f8;} QListWidget {background:#e8edf5;border:1px solid #dae2f0;border-radius:8px;padding:8px;} QListWidget::item {background:white;border:1px solid #dae2f0;border-radius:8px;padding:6px;color:#263246;} QListWidget::item:selected {background:#dbe6ff;border:2px solid #416ae6;}')

    def load_from_viewer(self):
        self.entries.clear()
        self.grid.clear()
        if not getattr(self.viewer, 'path', None):
            self.info_label.setText(tr('열려 있는 PDF가 없습니다.'))
            return
        try:
            source = self.viewer.stage_current_preview(display=False)
        except Exception:
            source = self.viewer.path
        password = getattr(self.viewer, 'password', '')
        with open_pdf(source, password) as doc:
            for index in range(len(doc)):
                self.entries.append({
                    'kind': 'page',
                    'path': Path(source),
                    'password': password,
                    'page_index': index,
                    'rotate': 0,
                })
        self._rebuild_grid()

    def _render_icon(self, entry: dict) -> QIcon:
        if entry['kind'] == 'blank':
            img = QImage(120, 160, QImage.Format_RGB888)
            img.fill(Qt.white)
            return QIcon(QPixmap.fromImage(img))
        with open_pdf(entry['path'], entry.get('password', '')) as doc:
            page = doc[entry['page_index']]
            if entry['rotate']:
                page.set_rotation((page.rotation + entry['rotate']) % 360)
            scale = min(132 / max(page.rect.width, 1), 174 / max(page.rect.height, 1))
            pix = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            return QIcon(QPixmap.fromImage(image))

    def _rebuild_grid(self):
        self.grid.clear()
        for idx, entry in enumerate(self.entries):
            label = tr('빈 페이지') if entry['kind'] == 'blank' else f"{entry['page_index'] + 1}p"
            if entry['rotate']:
                label += f" ({entry['rotate']}°)"
            item = QListWidgetItem(self._render_icon(entry), f"{idx + 1}. {label}")
            item.setData(Qt.UserRole, idx)
            item.setTextAlignment(Qt.AlignCenter)
            self.grid.addItem(item)
        self.info_label.setText(tr('총 {count}페이지', count=len(self.entries)))

    def _sync_order_from_grid(self):
        order = [self.grid.item(i).data(Qt.UserRole) for i in range(self.grid.count())]
        self.entries = [self.entries[i] for i in order if 0 <= i < len(self.entries)]
        self._rebuild_grid()

    def _selected_indices(self) -> list[int]:
        rows = sorted({self.grid.row(item) for item in self.grid.selectedItems()})
        return rows if rows else ([0] if self.entries else [])

    def rotate_selected(self, delta: int):
        for row in self._selected_indices():
            self.entries[row]['rotate'] = (self.entries[row]['rotate'] + delta) % 360
        self._rebuild_grid()

    def duplicate_selected(self):
        rows = self._selected_indices()
        if not rows:
            return
        offset = 0
        for row in rows:
            copy_entry = dict(self.entries[row + offset])
            self.entries.insert(row + offset + 1, copy_entry)
            offset += 1
        self._rebuild_grid()

    def insert_blank_after(self):
        rows = self._selected_indices()
        pos = (rows[-1] + 1) if rows else len(self.entries)
        self.entries.insert(pos, {'kind': 'blank', 'rotate': 0, 'width': 595.0, 'height': 842.0})
        self._rebuild_grid()

    def insert_pdf_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('끼워넣을 PDF 선택'), '', 'PDF (*.pdf)')
        if not path:
            return
        try:
            with open_pdf(path) as doc:
                rows = self._selected_indices()
                pos = (rows[-1] + 1) if rows else len(self.entries)
                for offset in range(len(doc)):
                    self.entries.insert(pos + offset, {
                        'kind': 'page',
                        'path': Path(path),
                        'password': '',
                        'page_index': offset,
                        'rotate': 0,
                    })
            self._rebuild_grid()
        except Exception as error:
            QMessageBox.warning(self, tr('PDF 열기 실패'), str(error))

    def delete_selected(self):
        rows = set(self._selected_indices())
        if not rows or len(rows) >= len(self.entries):
            QMessageBox.warning(self, tr('페이지 삭제'), tr('한 페이지 이상 남겨 주세요.'))
            return
        self.entries = [entry for idx, entry in enumerate(self.entries) if idx not in rows]
        self._rebuild_grid()

    def _build_pdf(self, target: Path, indices: list[int] | None = None):
        chosen = [self.entries[i] for i in indices] if indices is not None else self.entries
        cache: dict[tuple[str, str], pdf.Document] = {}
        try:
            with pdf.open() as out:
                for entry in chosen:
                    if entry['kind'] == 'blank':
                        page = out.new_page(width=entry.get('width', 595.0), height=entry.get('height', 842.0))
                        if entry['rotate']:
                            page.set_rotation(entry['rotate'])
                    else:
                        key = (str(entry['path']), entry.get('password', ''))
                        if key not in cache:
                            src = pdf.open(entry['path'])
                            if src.needs_pass:
                                src.authenticate(entry.get('password', ''))
                            cache[key] = src
                        src_doc = cache[key]
                        out.insert_pdf(src_doc, from_page=entry['page_index'], to_page=entry['page_index'])
                        if entry['rotate']:
                            out[-1].set_rotation((out[-1].rotation + entry['rotate']) % 360)
                out.save(target, garbage=4, deflate=True)
        finally:
            for doc in cache.values():
                doc.close()

    def extract_selected(self):
        rows = self._selected_indices()
        if not rows:
            return
        base = getattr(self.viewer, 'original_path', None) or Path.home() / 'extracted.pdf'
        target, _ = QFileDialog.getSaveFileName(self, tr('선택 페이지 저장'), str(base.with_name(base.stem + '_추출.pdf')), 'PDF (*.pdf)')
        if not target:
            return
        try:
            self._build_pdf(Path(target), rows)
            QMessageBox.information(self, tr('추출 완료'), tr('{file}으로 저장했습니다.', file=Path(target).name))
        except Exception as error:
            QMessageBox.warning(self, tr('추출 실패'), str(error))

    def commit_to_viewer(self):
        if not self.entries:
            return
        import tempfile
        owner = tempfile.TemporaryDirectory(prefix='eoing-multi-')
        target = Path(owner.name) / 'multitool.pdf'
        try:
            self._build_pdf(target)
            self.viewer.apply_preview(str(target), getattr(self.viewer, 'password', ''), owner, label='페이지 멀티툴')
            self.close_requested.emit()
        except Exception as error:
            owner.cleanup()
            QMessageBox.warning(self, tr('멀티툴 적용 실패'), str(error))
