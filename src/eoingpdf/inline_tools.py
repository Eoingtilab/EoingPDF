"""Stirling-style right-hand PDF Tools and PDF Processor (Pipelines) panel."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from .action_icons import set_action_icon, tool_icon
from .advanced import TOOLS
from .localization import tr
from .pipeline import DEFAULT_PIPELINES, expected_extension, load_custom_pipelines, save_custom_pipelines
from .sdk_theme import apply_style
from .tool_catalog import BY_KEY, CATEGORIES, find_tools
from .transform_process import TransformWorker

INLINE_SUPPORTED = frozenset(TOOLS)


class InlineToolRunner(QWidget):
    """Inline parameter & execution card inside the right sidebar (no nested modals)."""

    def __init__(self, viewer, on_back):
        super().__init__(viewer)
        self.viewer = viewer
        self.on_back = on_back
        self.current_key = 'target_size'
        self.worker = None
        self.preview_owner = None
        self.preview_target = ''
        self.preview_password = ''
        self.preview_success = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        back_btn = QPushButton(tr('← 목록'))
        back_btn.setAutoDefault(False)
        set_action_icon(back_btn, 'previous')
        back_btn.clicked.connect(self._go_back)
        header.addWidget(back_btn)
        self.title = QLabel()
        self.title.setStyleSheet('font-weight:700;font-size:14px;')
        header.addWidget(self.title, 1)
        layout.addLayout(header)

        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setStyleSheet('color:#657187;font-size:12px;')
        layout.addWidget(self.description)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        form_wrap = QWidget()
        self.form = QFormLayout(form_wrap)
        self.form.setContentsMargins(0, 4, 4, 4)

        self.page_range = QLineEdit()
        self.page_range.setPlaceholderText(tr('비우면 전체 · 예: 1-3, 5'))
        self.rotation_combo = QComboBox()
        for label, deg in ((tr('시계 90°'), 90), ('180°', 180), (tr('반시계 90° (270°)'), 270)):
            self.rotation_combo.addItem(label, deg)
        self.paper_combo = QComboBox()
        for label, key in (('A4', 'A4'), (tr('A4 가로'), 'A4_LANDSCAPE'), ('A3', 'A3'), ('Letter', 'LETTER'), ('B5', 'B5')):
            self.paper_combo.addItem(label, key)
        self.number_pos = QComboBox()
        for label, key in ((tr('하단 중앙'), 'bottom-center'), (tr('하단 오른쪽'), 'bottom-right'), (tr('상단 중앙'), 'top-center')):
            self.number_pos.addItem(label, key)
        self.number_start = QSpinBox()
        self.number_start.setRange(1, 999999)
        self.number_start.setValue(1)

        self.target_mb = QDoubleSpinBox()
        self.target_mb.setRange(0.05, 2000)
        self.target_mb.setValue(10.0)
        self.target_mb.setSuffix(' MB')
        self.best_effort_check = QCheckBox(tr('목표 초과 시 최소 용량으로 저장'))
        self.best_effort_check.setChecked(True)

        self.watermark_text = QLineEdit()
        self.watermark_text.setPlaceholderText(tr('예: 대외비 · 검토용'))
        self.watermark_opacity = QDoubleSpinBox()
        self.watermark_opacity.setRange(0.05, 1.0)
        self.watermark_opacity.setSingleStep(0.05)
        self.watermark_opacity.setValue(0.25)

        self.image_path = QLineEdit()
        self.image_path.setReadOnly(True)
        self.image_btn = QPushButton(tr('파일 선택'))
        set_action_icon(self.image_btn, 'open')
        self.image_btn.clicked.connect(self._pick_image)
        self.image_box = QWidget()
        img_l = QHBoxLayout(self.image_box)
        img_l.setContentsMargins(0, 0, 0, 0)
        img_l.addWidget(self.image_path, 1)
        img_l.addWidget(self.image_btn)

        self.qr_text = QLineEdit()
        self.qr_text.setPlaceholderText(tr('URL 또는 확인 문구 입력'))
        self.stamp_x = QDoubleSpinBox()
        self.stamp_y = QDoubleSpinBox()
        self.stamp_w = QDoubleSpinBox()
        self.stamp_x.setRange(0, 500)
        self.stamp_y.setRange(0, 500)
        self.stamp_w.setRange(5, 300)
        self.stamp_x.setValue(15)
        self.stamp_y.setValue(15)
        self.stamp_w.setValue(28)

        self.custom_terms = QPlainTextEdit()
        self.custom_terms.setMaximumHeight(68)
        self.custom_terms.setPlaceholderText(tr('자동 탐지 외 추가로 지울 단어 (쉼표/줄바꿈)'))

        self.split_ranges = QLineEdit()
        self.split_ranges.setPlaceholderText('1-3, 4-end')
        self.group_size = QSpinBox()
        self.group_size.setRange(1, 10000)
        self.group_size.setValue(1)
        self.max_mb = QDoubleSpinBox()
        self.max_mb.setRange(0.1, 500)
        self.max_mb.setValue(5.0)
        self.max_mb.setSuffix(' MB')

        self.insert_after = QSpinBox()
        self.insert_after.setRange(0, 10000)
        self.insert_after.setValue(1)
        self.insert_count = QSpinBox()
        self.insert_count.setRange(1, 50)
        self.insert_count.setValue(1)

        self.user_pw = QLineEdit()
        self.user_pw.setEchoMode(QLineEdit.Password)
        self.owner_pw = QLineEdit()
        self.owner_pw.setEchoMode(QLineEdit.Password)
        self.decrypt_pw = QLineEdit()
        self.decrypt_pw.setEchoMode(QLineEdit.Password)
        self.decrypt_pw.setPlaceholderText(tr('비우면 현재 열람 암호 사용'))
        self.overlay_pw = QLineEdit()
        self.overlay_pw.setEchoMode(QLineEdit.Password)
        self.overlay_pw.setPlaceholderText(tr('암호가 있는 배경 PDF일 때만 입력'))
        self.allow_print = QCheckBox(tr('인쇄 허용'))
        self.allow_print.setChecked(True)
        self.allow_copy = QCheckBox(tr('복사 허용'))
        self.allow_edit = QCheckBox(tr('수정 허용'))
        self.allow_annot = QCheckBox(tr('주석 허용'))

        self.bates_prefix = QLineEdit()
        self.bates_start = QSpinBox()
        self.bates_start.setRange(1, 999999)
        self.bates_start.setValue(1)
        self.bates_digits = QSpinBox()
        self.bates_digits.setRange(1, 10)
        self.bates_digits.setValue(6)
        self.bates_hide_old = QCheckBox(tr('기존 번호 가리기'))

        self.toc_text = QPlainTextEdit()
        self.toc_text.setMaximumHeight(84)
        self.toc_text.setPlaceholderText(tr('제목 | 페이지 (예: 1장 서론 | 1)'))
        self.auto_toc_check = QCheckBox(tr('제목 글자 크기에서 자동 추출'))
        self.auto_toc_check.setChecked(True)

        self.attach_mode = QComboBox()
        for label, key in ((tr('첨부 파일 ZIP 추출'), 'extract'), (tr('새 파일 첨부'), 'add'), (tr('첨부 파일 모두 제거'), 'remove')):
            self.attach_mode.addItem(label, key)

        self.overlay_fg = QCheckBox(tr('원본 위에 겹치기 (해제 시 배경으로)'))
        self.overlay_fg.setChecked(True)

        self._rows = [
            ('page_range', tr('페이지 범위'), self.page_range, {'rotate', 'page_numbers', 'qr_stamp'}),
            ('rotation', tr('회전 각도'), self.rotation_combo, {'rotate'}),
            ('paper', tr('용지 규격'), self.paper_combo, {'scale_pages', 'insert_blank'}),
            ('num_pos', tr('번호 위치'), self.number_pos, {'page_numbers'}),
            ('num_start', tr('시작 번호'), self.number_start, {'page_numbers'}),
            ('target_mb', tr('목표 용량'), self.target_mb, {'target_size'}),
            ('best_effort', '', self.best_effort_check, {'target_size'}),
            ('wm_text', tr('워터마크 문구'), self.watermark_text, {'watermark_text'}),
            ('wm_opacity', tr('불투명도'), self.watermark_opacity, {'watermark_text', 'watermark_png'}),
            ('img_path', tr('선택 파일'), self.image_box, {'watermark_png', 'overlay_pdf', 'attachments'}),
            ('overlay_fg', '', self.overlay_fg, {'overlay_pdf'}),
            ('overlay_pw', tr('배경 PDF 암호'), self.overlay_pw, {'overlay_pdf'}),
            ('qr_text', tr('QR 내용'), self.qr_text, {'qr_stamp'}),
            ('stamp_x', tr('가로 위치(mm)'), self.stamp_x, {'qr_stamp'}),
            ('stamp_y', tr('세로 위치(mm)'), self.stamp_y, {'qr_stamp'}),
            ('stamp_w', tr('QR 너비(mm)'), self.stamp_w, {'qr_stamp'}),
            ('custom_terms', tr('추가 가릴 단어'), self.custom_terms, {'redact', 'ocr_redact'}),
            ('split_ranges', tr('분할 범위'), self.split_ranges, {'split_ranges'}),
            ('group_size', tr('묶음 페이지 수'), self.group_size, {'split_groups'}),
            ('max_mb', tr('파일당 최대 용량'), self.max_mb, {'split_size'}),
            ('insert_after', tr('몇 페이지 뒤에'), self.insert_after, {'insert_blank'}),
            ('insert_count', tr('추가 장수'), self.insert_count, {'insert_blank'}),
            ('user_pw', tr('열기 암호'), self.user_pw, {'encrypt', 'permissions'}),
            ('owner_pw', tr('소유자 암호'), self.owner_pw, {'encrypt', 'permissions'}),
            ('decrypt_pw', tr('해제할 암호'), self.decrypt_pw, {'decrypt'}),
            ('allow_print', '', self.allow_print, {'encrypt', 'permissions'}),
            ('allow_copy', '', self.allow_copy, {'encrypt', 'permissions'}),
            ('allow_edit', '', self.allow_edit, {'permissions'}),
            ('allow_annot', '', self.allow_annot, {'permissions'}),
            ('bates_prefix', tr('접두어'), self.bates_prefix, {'bates'}),
            ('bates_start', tr('시작 번호'), self.bates_start, {'bates'}),
            ('bates_digits', tr('자리 수'), self.bates_digits, {'bates'}),
            ('bates_hide_old', '', self.bates_hide_old, {'bates'}),
            ('auto_toc', '', self.auto_toc_check, {'bookmarks'}),
            ('toc_text', tr('목차 내용'), self.toc_text, {'bookmarks'}),
            ('attach_mode', tr('첨부 작업'), self.attach_mode, {'attachments'}),
        ]
        for _id, lbl, widget, _ops in self._rows:
            self.form.addRow(lbl, widget)

        scroll.setWidget(form_wrap)
        layout.addWidget(scroll, 1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        layout.addWidget(self.progress)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet('font-size:12px;')
        layout.addWidget(self.status)

        btn_row = QHBoxLayout()
        self.apply_btn = QPushButton(tr('현재 PDF에 적용'))
        self.apply_btn.setObjectName('primary')
        set_action_icon(self.apply_btn, 'play')
        self.apply_btn.clicked.connect(lambda: self._run(preview=True))
        btn_row.addWidget(self.apply_btn)

        self.save_btn = QPushButton(tr('새 파일 저장'))
        set_action_icon(self.save_btn, 'save')
        self.save_btn.clicked.connect(lambda: self._run(preview=False))
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        self.advanced_btn = QPushButton(tr('상세 옵션 창에서 열기'))
        set_action_icon(self.advanced_btn, 'settings')
        self.advanced_btn.clicked.connect(lambda: self.viewer.open_advanced_dialog(self.current_key))
        layout.addWidget(self.advanced_btn)

    def _go_back(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            return
        self.on_back()

    def _pick_image(self):
        if self.current_key == 'overlay_pdf':
            filt = 'PDF (*.pdf)'
        elif self.current_key == 'attachments':
            filt = tr('모든 파일 (*.*)')
        else:
            filt = 'PNG (*.png)'
        path, _ = QFileDialog.getOpenFileName(self, tr('파일 선택'), '', filt)
        if path:
            self.image_path.setText(path)

    def load_tool(self, key: str):
        self.current_key = key
        name, desc = TOOLS.get(key, (key, ''))
        self.title.setText(tr(name))
        self.description.setText(tr(desc))
        self.progress.setValue(0)
        self.status.setText('')
        for _id, _lbl, widget, ops in self._rows:
            vis = key in ops
            widget.setVisible(vis)
            lbl = self.form.labelForField(widget)
            if lbl is not None:
                lbl.setVisible(vis)
        can_preview = expected_extension(key) == '.pdf' and key not in {'attachments', 'encrypt', 'permissions'}
        self.apply_btn.setVisible(can_preview)
        self.advanced_btn.setVisible(key in {'stamp', 'replace_image', 'auto_forms'})
        if key == 'insert_blank' and getattr(self.viewer, 'page', None):
            self.insert_after.setValue(self.viewer.page.value())

    def _run(self, preview: bool):
        if self.worker and self.worker.isRunning():
            return
        if not getattr(self.viewer, 'path', None):
            self.status.setText(tr('먼저 PDF 문서를 열어 주세요.'))
            return
        key = self.current_key
        if key in {'stamp', 'replace_image', 'auto_forms'}:
            self.viewer.open_advanced_dialog(key)
            return
        try:
            source = self.viewer.stage_current_preview(display=False)
        except Exception as error:
            self.status.setText(str(error))
            return
        ext = '.zip' if (key == 'attachments' and self.attach_mode.currentData() == 'extract') else expected_extension(key)
        if preview:
            self.preview_owner = tempfile.TemporaryDirectory(prefix='eoing-inline-')
            target = str(Path(self.preview_owner.name) / 'preview.pdf')
            self.preview_target = target
            self.preview_password = ''
            self.preview_success = False
        else:
            base = getattr(self.viewer, 'original_path', source)
            target, _ = QFileDialog.getSaveFileName(
                self,
                tr('새 결과 저장'),
                str(base.with_name(f'{base.stem}_{tr(TOOLS[key][0])}{ext}')),
                f'{ext[1:].upper()} (*{ext})',
            )
            if not target:
                return
        options = {
            'source': str(source),
            'target': target,
            'operation': key,
            'password': (self.decrypt_pw.text() or getattr(self.viewer, 'password', '')) if key == 'decrypt' else getattr(self.viewer, 'password', ''),
            'user_password': self.user_pw.text(),
            'owner_password': self.owner_pw.text(),
            'allow_print': self.allow_print.isChecked(),
            'allow_copy': self.allow_copy.isChecked(),
            'allow_edit': self.allow_edit.isChecked(),
            'allow_annotate': self.allow_annot.isChecked(),
            'watermark_text': self.watermark_text.text(),
            'watermark_image': self.image_path.text(),
            'watermark_opacity': self.watermark_opacity.value(),
            'split_ranges': self.split_ranges.text(),
            'group_size': self.group_size.value(),
            'target_mb': self.target_mb.value(),
            'allow_best_effort': self.best_effort_check.isChecked(),
            'custom_terms': self.custom_terms.toPlainText(),
            'rotation': self.rotation_combo.currentData(),
            'page_range': self.page_range.text(),
            'number_position': self.number_pos.currentData(),
            'number_start': self.number_start.value(),
            'paper_size': self.paper_combo.currentData(),
            'insert_after': self.insert_after.value(),
            'insert_count': self.insert_count.value(),
            'overlay_path': self.image_path.text(),
            'overlay_password': self.overlay_pw.text(),
            'overlay_foreground': self.overlay_fg.isChecked(),
            'max_mb': self.max_mb.value(),
            'bates_prefix': self.bates_prefix.text(),
            'bates_start': self.bates_start.value(),
            'bates_digits': self.bates_digits.value(),
            'bates_hide_old': self.bates_hide_old.isChecked(),
            'toc_text': self.toc_text.toPlainText(),
            'auto_toc': self.auto_toc_check.isChecked(),
            'attachment_mode': self.attach_mode.currentData(),
            'attachment_path': self.image_path.text(),
            'qr_text': self.qr_text.text(),
            'stamp_pages': self.page_range.text() or (str(self.viewer.page.value()) if getattr(self.viewer, 'page', None) else '1'),
            'stamp_x_mm': self.stamp_x.value(),
            'stamp_y_mm': self.stamp_y.value(),
            'stamp_width_mm': self.stamp_w.value(),
        }
        self.apply_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.status.setText(tr('내 PC에서 처리 중…'))
        self.worker = TransformWorker(options, self)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.result.connect(self._on_result)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_result(self, success: bool, message: str):
        self.preview_success = success
        self.status.setText(message)

    def _on_finished(self):
        self.apply_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.user_pw.clear()
        self.owner_pw.clear()
        self.decrypt_pw.clear()
        self.overlay_pw.clear()
        if self.preview_owner:
            owner, self.preview_owner = self.preview_owner, None
            if self.preview_success:
                try:
                    self.viewer.apply_preview(self.preview_target, '', owner, label=TOOLS[self.current_key][0])
                    self.progress.setValue(100)
                except Exception as error:
                    owner.cleanup()
                    self.status.setText(str(error))
            else:
                owner.cleanup()


class PipelinePanel(QWidget):
    """Stirling-style PDF Processor for sequential multi-step workflows."""

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.steps: list[dict] = []
        self.worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(QLabel(tr('프리셋 불러오기')))
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.preset_combo.setMinimumContentsLength(6)
        self._reload_presets()
        preset_row.addWidget(self.preset_combo, 1)
        load_btn = QPushButton(tr('적용'))
        set_action_icon(load_btn, 'play')
        load_btn.clicked.connect(self._load_selected_preset)
        preset_row.addWidget(load_btn)
        layout.addLayout(preset_row)

        add_row = QHBoxLayout()
        self.add_combo = QComboBox()
        self.add_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.add_combo.setMinimumContentsLength(6)
        for key, (name, _desc) in TOOLS.items():
            self.add_combo.addItem(tr(name), key)
        add_row.addWidget(self.add_combo, 1)
        add_btn = QPushButton(tr('+ 추가'))
        set_action_icon(add_btn, 'tools')
        add_btn.clicked.connect(self._add_step)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self.steps_list = QListWidget()
        layout.addWidget(self.steps_list, 1)

        ctrl_row = QHBoxLayout()
        for label, cb, icon_name in ((tr('↑'), lambda: self._move(-1), 'up'),
                                     (tr('↓'), lambda: self._move(1), 'down'),
                                     (tr('삭제'), self._remove_step, 'delete'),
                                     (tr('저장'), self._save_preset, 'save')):
            b = QPushButton(label)
            set_action_icon(b, icon_name)
            b.clicked.connect(cb)
            ctrl_row.addWidget(b)
        layout.addLayout(ctrl_row)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        layout.addWidget(self.progress)
        self.status = QLabel(tr('여러 도구를 순서대로 묶어 한 번에 실행합니다.'))
        self.status.setWordWrap(True)
        self.status.setStyleSheet('font-size:12px;')
        layout.addWidget(self.status)

        self.run_btn = QPushButton(tr('파이프라인 실행'))
        self.run_btn.setObjectName('primary')
        set_action_icon(self.run_btn, 'play')
        self.run_btn.clicked.connect(self._run_pipeline)
        layout.addWidget(self.run_btn)
        self._load_selected_preset()

    def _reload_presets(self):
        self.preset_combo.clear()
        for preset in list(DEFAULT_PIPELINES) + load_custom_pipelines():
            self.preset_combo.addItem(tr(preset['name']), preset)

    def _load_selected_preset(self):
        preset = self.preset_combo.currentData()
        if not preset:
            return
        self.steps = [dict(step) for step in preset.get('steps', [])]
        self._refresh_list()

    def _add_step(self):
        op = self.add_combo.currentData()
        if op:
            self.steps.append({'operation': op, 'options': {}})
            self._refresh_list()

    def _move(self, delta: int):
        row = self.steps_list.currentRow()
        target = row + delta
        if 0 <= row < len(self.steps) and 0 <= target < len(self.steps):
            self.steps[row], self.steps[target] = self.steps[target], self.steps[row]
            self._refresh_list()
            self.steps_list.setCurrentRow(target)

    def _remove_step(self):
        row = self.steps_list.currentRow()
        if 0 <= row < len(self.steps):
            self.steps.pop(row)
            self._refresh_list()

    def _save_preset(self):
        if not self.steps:
            return
        name, ok = QInputDialog.getText(self, tr('파이프라인 저장'), tr('프리셋 이름을 입력해 주세요.'))
        if ok and name.strip():
            custom = load_custom_pipelines()
            custom.append({'name': name.strip(), 'steps': self.steps})
            save_custom_pipelines(custom)
            self._reload_presets()

    def _refresh_list(self):
        self.steps_list.clear()
        for idx, step in enumerate(self.steps, 1):
            op = step['operation']
            title = tr(TOOLS[op][0]) if op in TOOLS else op
            item = QListWidgetItem(f'{idx}. {title}')
            item.setIcon(tool_icon(op, BY_KEY[op].category if op in BY_KEY else 'optimize', self.steps_list))
            self.steps_list.addItem(item)

    def _run_pipeline(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.steps:
            self.status.setText(tr('실행할 단계를 추가해 주세요.'))
            return
        if not getattr(self.viewer, 'path', None):
            self.status.setText(tr('먼저 PDF 문서를 열어 주세요.'))
            return
        ext = expected_extension(self.steps[-1]['operation'])
        base = getattr(self.viewer, 'original_path', self.viewer.path)
        target, _ = QFileDialog.getSaveFileName(
            self,
            tr('파이프라인 결과 저장'),
            str(base.with_name(f'{base.stem}_파이프라인{ext}')),
            f'{ext[1:].upper()} (*{ext})',
        )
        if not target:
            return
        try:
            source = self.viewer.stage_current_preview(display=False)
        except Exception as error:
            self.status.setText(str(error))
            return
        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self.status.setText(tr('파이프라인을 실행하고 있습니다…'))
        self.worker = TransformWorker(
            {
                'operation': 'pipeline',
                'source': str(source),
                'target': target,
                'password': getattr(self.viewer, 'password', ''),
                'steps': self.steps,
            },
            self,
        )
        self.worker.progress.connect(self.progress.setValue)
        self.worker.result.connect(lambda _ok, msg: self.status.setText(msg))
        self.worker.finished.connect(lambda: self.run_btn.setEnabled(True))
        self.worker.start()


class RightToolsDock(QScrollArea):
    """Right-hand Stirling-style PDF Tools + PDF Processor panel preserving all legacy hooks."""

    def __init__(self, viewer):
        super().__init__(viewer)
        from .tool_browser import ToolDelegate
        self.viewer = viewer
        self.setObjectName('toolsPanel')
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(self.Shape.NoFrame)

        container = QWidget()
        container.setObjectName('editingActions')
        self._container = container
        self.set_panel_width(296)
        self.setWidget(container)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Header row preserving viewer.close_tools_button
        heading_row = QHBoxLayout()
        heading = QLabel(tr('PDF 도구 · 프로세서'))
        heading.setObjectName('toolsHeading')
        heading_row.addWidget(heading, 1)
        close_btn = QPushButton()
        close_btn.setAutoDefault(False)
        set_action_icon(close_btn, 'close')
        close_btn.setFixedSize(28, 28)
        apply_style(close_btn, 'QPushButton {padding:0;}')
        close_btn.setToolTip(tr('도구 목록 닫기'))
        close_btn.setAccessibleName(tr('도구 목록 닫기'))
        close_btn.clicked.connect(lambda: viewer.editing_toggle.setChecked(False))
        viewer.close_tools_button = close_btn
        heading_row.addWidget(close_btn)
        outer.addLayout(heading_row)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        # Tab 1: Stirling-style Search + Recommended + Full Rich Catalog + Legacy Footer
        tools_host = QWidget()
        tools_layout = QVBoxLayout(tools_host)
        tools_layout.setContentsMargins(0, 6, 0, 0)
        self.tool_stack = QStackedWidget()
        tools_layout.addWidget(self.tool_stack, 1)

        catalog_page = QWidget()
        cat_layout = QVBoxLayout(catalog_page)
        cat_layout.setContentsMargins(2, 2, 2, 2)
        cat_layout.setSpacing(6)

        # 1. Search + Category Filter at very top (Stirling PDF style)
        self.search_input = QLineEdit()
        self.search_input.setMinimumWidth(0)
        self.search_input.setPlaceholderText(tr('도구 검색 (Ctrl+K) · 65+ PDF 도구'))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.refresh_catalog)
        cat_layout.addWidget(self.search_input)

        self.cat_combo = QComboBox()
        self.cat_combo.setMinimumWidth(0)
        self.cat_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cat_combo.setMinimumContentsLength(6)
        self.cat_combo.addItem(tr('전체 도구 ({count})', count=len(BY_KEY)), 'all')
        self.cat_combo.addItem(tr('추천 도구'), 'recommended')
        for grp in CATEGORIES:
            self.cat_combo.addItem(tr(grp.title), grp.key)
        self.cat_combo.currentIndexChanged.connect(self.refresh_catalog)
        cat_layout.addWidget(self.cat_combo)

        # 2. RECOMMENDED crisp 2-column grid
        rec_lbl = QLabel(tr('RECOMMENDED · 추천 도구'))
        rec_lbl.setStyleSheet('font-size:10px;font-weight:700;color:#64748b;letter-spacing:0.5px;padding-top:2px;')
        cat_layout.addWidget(rec_lbl)
        rec_grid = QGridLayout()
        rec_grid.setSpacing(4)
        for idx, (key, label, icon_name) in enumerate((
            ('multi_tool', '멀티툴', 'thumbnail'),
            ('merge', '빠른 병합', 'pages'),
            ('save_as', '내보내기', 'save'),
            ('target_size', '용량 압축', 'optimize'),
            ('searchable', 'OCR 검색', 'scan'),
            ('redact', '정보 삭제', 'security'),
        )):
            rb = QPushButton(tr(label))
            rb.setObjectName('recommendedChip')
            rb.setAutoDefault(False)
            rb.setMinimumWidth(0)
            rb.setProperty('alignLeft', True)
            set_action_icon(rb, icon_name)
            rb.clicked.connect(lambda _c=False, k=key: self.activate_tool(k))
            rec_grid.addWidget(rb, idx // 2, idx % 2)
        cat_layout.addLayout(rec_grid)

        # 3. ALL TOOLS scrollable rich delegate catalog
        all_lbl = QLabel(tr('ALL TOOLS · 전체 도구 ({count})', count=len(BY_KEY)))
        all_lbl.setStyleSheet('font-size:10px;font-weight:700;color:#64748b;letter-spacing:0.5px;padding-top:4px;')
        cat_layout.addWidget(all_lbl)

        self.tool_list = QListWidget()
        self.tool_list.setObjectName('stirlingToolCatalog')
        self.tool_list.setMinimumWidth(0)
        self.tool_list.setMinimumHeight(240)
        self.tool_list.setSpacing(0)
        self.tool_list.setWordWrap(True)
        self.tool_list.setUniformItemSizes(False)
        self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tool_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tool_list.setResizeMode(QListView.Adjust)
        self.tool_list.setItemDelegate(ToolDelegate(self.tool_list))
        self.tool_list.itemClicked.connect(lambda item: self.activate_tool(item.data(Qt.UserRole)))
        cat_layout.addWidget(self.tool_list, 1)

        def qbtn(text, cb, icon_name):
            b = QPushButton(tr(text))
            b.setAutoDefault(False)
            b.setMinimumWidth(0)
            b.setToolTip(tr(text))
            set_action_icon(b, icon_name)
            b.clicked.connect(cb)
            return b

        # 4. Quick utilities card below catalog (preserves every legacy hook cleanly without crowding top)
        quick_lbl = QLabel(tr('빠른 실행 · 편집'))
        quick_lbl.setStyleSheet('font-size:10px;font-weight:700;color:#64748b;letter-spacing:0.5px;padding-top:4px;')
        cat_layout.addWidget(quick_lbl)

        viewer.panel_all_tools_button = qbtn('도구 검색', viewer.show_all_tools, 'search')
        viewer.undo_button = qbtn('실행 취소', viewer.undo_edit, 'undo')
        viewer.redo_button = qbtn('다시 실행', viewer.redo_edit, 'redo')
        viewer.history_button = qbtn('변경 내역', lambda: viewer.open_history_dialog(), 'history')
        viewer.panel_scan_button = qbtn('스캔·OCR', lambda: viewer.show_all_tools('scan'), 'scan')
        viewer.panel_security_button = qbtn('보안·개인정보', lambda: viewer.show_all_tools('security'), 'security')
        viewer.panel_export_button = qbtn('복사·추출', lambda: viewer.show_all_tools('export'), 'export')
        viewer.panel_optimize_button = qbtn('압축·복구', lambda: viewer.show_all_tools('optimize'), 'optimize')
        viewer.form_button = qbtn('양식 입력', viewer.edit_form, 'form')
        viewer.page_tools_button = qbtn('페이지 정리', lambda: None, 'pages')
        viewer.view_tools_button = qbtn('복사·보기', lambda: None, 'copy')

        quick_grid = QGridLayout()
        quick_grid.setSpacing(4)
        quick_grid.addWidget(viewer.undo_button, 0, 0)
        quick_grid.addWidget(viewer.redo_button, 0, 1)
        full_buttons = (
            viewer.history_button, viewer.form_button,
            viewer.page_tools_button, viewer.view_tools_button,
            viewer.panel_scan_button, viewer.panel_security_button,
            viewer.panel_export_button, viewer.panel_optimize_button,
            viewer.panel_all_tools_button,
        )
        for row_idx, b in enumerate(full_buttons, start=1):
            b.setProperty('alignLeft', True)
            quick_grid.addWidget(b, row_idx, 0, 1, 2)
        cat_layout.addLayout(quick_grid)

        self.inline_runner = InlineToolRunner(viewer, lambda: self.tool_stack.setCurrentIndex(0))
        self.tool_stack.addWidget(catalog_page)
        self.tool_stack.addWidget(self.inline_runner)
        self.tabs.addTab(tools_host, tr('PDF 도구'))

        # Tab 2: Pipeline Processor
        self.pipeline_panel = PipelinePanel(viewer)
        self.tabs.addTab(self.pipeline_panel, tr('파이프라인'))

        apply_style(container, '''
            QWidget#editingActions {background:#ffffff;}
            QLabel#toolsHeading {color:#263246; font-weight:700; font-size:13px; padding:2px;}
            QTabWidget::pane {border:0;}
            QTabBar::tab {background:#eef2f8; color:#657187; border-radius:6px; padding:6px 12px; margin-right:4px; font-weight:600; font-size:12px;}
            QTabBar::tab:selected {background:#edf2ff; color:#183b8f; border:1px solid #c6d3e6;}
            QLineEdit, QComboBox {background:#f7f9fc; border:1px solid #dae2f0; border-radius:6px; padding:5px 8px; font-size:12px;}
            QPushButton {background:#f7f9fc; border:1px solid #dae2f0; padding:5px 7px; border-radius:6px; font-size:12px;}
            QPushButton[alignLeft="true"] {text-align:left; padding:5px 8px;}
            QPushButton#recommendedChip {background:#f7f9fc; border:1px solid #dae2f0; font-weight:600;}
            QPushButton#recommendedChip:hover {background:#edf2ff; border-color:#7c9dfa;}
            QPushButton:hover {background:#edf2ff;}
            QPushButton#primary {background:#416ae6; color:white; border:0; font-weight:600; padding:7px 10px;}
            QPushButton#primary:hover {background:#3e61d8;}
            QListWidget#stirlingToolCatalog {background:#ffffff; border:1px solid #e2e7ef; border-radius:8px; outline:0;}
            QListWidget#stirlingToolCatalog::item {background:#ffffff; border:1px solid #f0f3f8; border-radius:7px; margin:2px 3px;}
            QListWidget#stirlingToolCatalog::item:hover {background:#f1f5fb; border-color:#c6d3e6;}
            QListWidget#stirlingToolCatalog::item:selected {background:#dbe6ff; color:#183b8f; border:1px solid #7c9dfa;}
        ''')
        apply_style(self, 'QScrollArea#toolsPanel {background:#ffffff; border-left:1px solid #e2e7ef;}')
        self.refresh_catalog()

    def set_panel_width(self, width: int):
        changed = False
        if self.width() != width:
            self.setFixedWidth(width)
            changed = True
        inner = max(220, width - 16)
        if self._container.maximumWidth() != inner:
            self._container.setMaximumWidth(inner)
            changed = True
        if changed and hasattr(self, 'tool_list'):
            self.tool_list.doItemsLayout()

    def refresh_catalog(self):
        query = self.search_input.text()
        category = self.cat_combo.currentData() or 'all'
        entries = find_tools(query, category)
        self.tool_list.clear()
        for entry in entries:
            title = tr(entry.title)
            desc = tr(entry.description)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, entry.key)
            item.setData(Qt.UserRole + 1, title)
            item.setData(Qt.UserRole + 2, desc)
            item.setIcon(tool_icon(entry.key, entry.category, self.tool_list))
            item.setToolTip(f'{title} — {desc}')
            self.tool_list.addItem(item)

    def activate_tool(self, key: str):
        if key == 'pipeline':
            self.tabs.setCurrentIndex(1)
            return
        if key in INLINE_SUPPORTED and key not in {'stamp', 'replace_image', 'auto_forms'}:
            self.tabs.setCurrentIndex(0)
            self.inline_runner.load_tool(key)
            self.tool_stack.setCurrentIndex(1)
            return
        self.viewer.diagnostic_action(key)

    def focus_search(self):
        self.setVisible(True)
        self.viewer.editing_toggle.setChecked(True)
        self.tabs.setCurrentIndex(0)
        self.tool_stack.setCurrentIndex(0)
        self.search_input.setFocus()
        self.search_input.selectAll()
