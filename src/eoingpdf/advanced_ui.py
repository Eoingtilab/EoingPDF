"""On-demand PDF utilities; no resident process and no password persistence."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QFileDialog, QCheckBox, QProgressBar, QDoubleSpinBox, QSpinBox, QWidget, QScrollArea)
from .advanced import TOOLS
from .transform_process import TransformWorker
from .localization import tr


class AdvancedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.compare_pair = None
        self.setWindowTitle(tr('어잉PDF · 암호 및 보조 도구'))
        self.resize(620, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        self.tool = QComboBox()
        for key, (name, _) in TOOLS.items():
            self.tool.addItem(tr(name), key)
        layout.addWidget(self.tool)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.source = QLineEdit()
        self.source.setReadOnly(True)
        self.pick = QPushButton(tr('PDF 선택'))
        self.pick.clicked.connect(self.choose)
        row = QHBoxLayout()
        row.addWidget(self.source, 1)
        row.addWidget(self.pick)
        layout.addLayout(row)
        form_body = QWidget()
        form = self.form = QFormLayout(form_body)
        form.setContentsMargins(0, 0, 8, 0)
        self.password = QLineEdit()
        self.user_password = QLineEdit()
        self.owner_password = QLineEdit()
        for field in (self.password, self.user_password, self.owner_password):
            field.setEchoMode(QLineEdit.Password)
            field.setMaxLength(256)
        form.addRow(tr('현재 PDF 암호'), self.password)
        form.addRow(tr('새 열기 암호'), self.user_password)
        form.addRow(tr('새 소유자 암호'), self.owner_password)
        self.watermark_text = QLineEdit()
        self.watermark_text.setMaxLength(200)
        self.watermark_text.setPlaceholderText(tr('예: 대외비 · 검토용'))
        form.addRow(tr('워터마크 문구'), self.watermark_text)
        self.watermark_image = QLineEdit()
        self.watermark_image.setReadOnly(True)
        self.image_row = QWidget()
        image_layout = QHBoxLayout(self.image_row)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.addWidget(self.watermark_image, 1)
        image_button = QPushButton(tr('이미지 선택'))
        image_button.clicked.connect(self.choose_watermark)
        image_layout.addWidget(image_button)
        self.vault_button = QPushButton(tr('도장 보관함'))
        self.vault_button.clicked.connect(self.choose_seal)
        image_layout.addWidget(self.vault_button)
        form.addRow(tr('이미지'), self.image_row)
        self.watermark_opacity = QDoubleSpinBox()
        self.watermark_opacity.setRange(.01, 1)
        self.watermark_opacity.setSingleStep(.05)
        self.watermark_opacity.setValue(.2)
        form.addRow(tr('불투명도'), self.watermark_opacity)
        self.split_ranges = QLineEdit()
        self.split_ranges.setPlaceholderText('1-3, 5, 8-end')
        self.split_ranges.setMaxLength(10000)
        form.addRow(tr('분할 범위'), self.split_ranges)
        self.group_size = QSpinBox()
        self.group_size.setRange(1, 100000)
        self.group_size.setValue(1)
        self.group_size.setSuffix(tr(' 페이지씩'))
        form.addRow(tr('묶음 크기'), self.group_size)
        self.target_mb = QDoubleSpinBox()
        self.target_mb.setRange(.05, 2000)
        self.target_mb.setValue(10)
        self.target_mb.setSuffix(' MB')
        form.addRow(tr('목표 용량'), self.target_mb)
        self.size_presets = QComboBox()
        self.size_presets.addItems(['10MB', '25MB', tr('직접 입력')])
        self.size_presets.currentIndexChanged.connect(lambda index: self.target_mb.setValue((10, 25)[index]) if index < 2 else None)
        self.target_mb.valueChanged.connect(self.sync_size_preset)
        form.addRow(tr('용량 선택'), self.size_presets)
        self.bates_prefix = QLineEdit()
        self.bates_prefix.setMaxLength(40)
        self.bates_start = QSpinBox()
        self.bates_start.setRange(1, 999999999)
        self.bates_digits = QSpinBox()
        self.bates_digits.setRange(1, 12)
        self.bates_digits.setValue(6)
        self.bates_hide_old = QCheckBox(tr('하단의 기존 숫자 번호 가리기'))
        self.bates_hide_old.setChecked(True)
        self.bates_cover = QCheckBox(tr('클릭 가능한 목차 표지 추가'))
        self.bates_fields = (self.bates_prefix, self.bates_start, self.bates_digits, self.bates_hide_old, self.bates_cover)
        for label, field in zip((tr('접두어'), tr('시작 번호'), tr('자리 수'), tr('기존 번호'), tr('목차 표지')), self.bates_fields):
            form.addRow(label, field)
        self.stamp_pages = QLineEdit('1')
        self.stamp_pages.setPlaceholderText(tr('예: 1, 3-5, 8-end · 비우면 전체'))
        self.stamp_pages.setMaxLength(10000)
        self.stamp_x = QDoubleSpinBox()
        self.stamp_y = QDoubleSpinBox()
        self.stamp_width = QDoubleSpinBox()
        for field, minimum, default in ((self.stamp_x, 0, 10), (self.stamp_y, 0, 10), (self.stamp_width, 1, 30)):
            field.setRange(minimum, 1000)
            field.setValue(default)
            field.setSuffix(' mm')
        self.stamp_flatten = QCheckBox(tr('전체 PDF를 300DPI 이미지로 합치기'))
        self.stamp_flatten.setChecked(True)
        self.stamp_fields = (self.stamp_pages, self.stamp_x, self.stamp_y, self.stamp_width, self.stamp_flatten)
        for label, field in zip((tr('찍을 페이지'), tr('왼쪽에서'), tr('위쪽에서'), tr('도장 너비'), tr('합치기')), self.stamp_fields):
            form.addRow(label, field)
        self.replace_choice = QPushButton(tr('원본 이미지 선택'))
        self.replace_choice.clicked.connect(self.choose_original_image)
        self.replace_selection = (0, '')
        self.source.textChanged.connect(self.reset_image_choice)
        form.addRow(tr('교체할 이미지'), self.replace_choice)
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setMinimumHeight(120)
        self.form_scroll.setWidget(form_body)
        layout.addWidget(self.form_scroll, 1)
        self.printing = QCheckBox(tr('인쇄 허용'))
        self.printing.setChecked(True)
        self.copying = QCheckBox(tr('텍스트 복사 허용'))
        layout.addWidget(self.printing)
        layout.addWidget(self.copying)
        notice = QLabel(tr('원본은 보존하며 새 파일로 저장합니다. 암호 설정 이외의 도구는 암호 없는 사본을 만듭니다. 암호는 저장하거나 전송하지 않습니다.'))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.status = QLabel(tr('PDF와 도구를 선택해 주세요.'))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.compare_button = QPushButton(tr('원본과 비교'))
        self.compare_button.hide()
        self.compare_button.clicked.connect(self.compare_saved)
        row.addWidget(self.compare_button)
        self.save = QPushButton(tr('새 PDF로 저장'))
        self.save.setObjectName('primary')
        self.save.clicked.connect(self.start)
        self.cancel = QPushButton(tr('닫기'))
        self.cancel.clicked.connect(self.reject)
        row.addWidget(self.save)
        row.addWidget(self.cancel)
        layout.addLayout(row)
        self.tool.currentIndexChanged.connect(self.changed)
        self.changed()

    def sync_size_preset(self, value):
        previous = self.size_presets.blockSignals(True)
        try:
            self.size_presets.setCurrentIndex({10: 0, 25: 1}.get(value, 2))
        finally:
            self.size_presets.blockSignals(previous)

    def changed(self):
        key = self.tool.currentData()
        self.replace_choice.setVisible(key == 'replace_image')
        self.replace_choice.setEnabled(key == 'replace_image')
        self.form.labelForField(self.replace_choice).setVisible(key == 'replace_image')
        self.vault_button.setVisible(key == 'stamp')
        if key != 'stamp' and self.watermark_image.text().lower().endswith('.eoseal'):
            self.watermark_image.clear()
        self.description.setText(tr(TOOLS[key][1]))
        for field in self.stamp_fields:
            field.setVisible(key == 'stamp')
            field.setEnabled(key == 'stamp')
            self.form.labelForField(field).setVisible(key == 'stamp')
        for field in self.bates_fields:
            field.setVisible(key == 'bates')
            field.setEnabled(key == 'bates')
            self.form.labelForField(field).setVisible(key == 'bates')
        for widget in (self.user_password, self.owner_password, self.printing, self.copying):
            widget.setEnabled(key == 'encrypt')
            widget.setVisible(key == 'encrypt')
        for field in (self.user_password, self.owner_password):
            self.form.labelForField(field).setVisible(key == 'encrypt')
        for field, visible in ((self.watermark_text, key == 'watermark_text'),
                               (self.image_row, key in {'watermark_png', 'stamp', 'replace_image'}),
                               (self.watermark_opacity, key in {'watermark_text', 'watermark_png'}),
                               (self.split_ranges, key == 'split_ranges'), (self.group_size, key == 'split_groups'),
                               (self.target_mb, key == 'target_size'), (self.size_presets, key == 'target_size')):
            field.setVisible(visible)
            field.setEnabled(visible)
            self.form.labelForField(field).setVisible(visible)
        self.save.setText(tr('분할 ZIP 저장') if key in {'split_ranges', 'split_groups', 'split_toc'} else
                          tr('SVG ZIP 저장') if key == 'svg' else tr('Markdown 저장') if key == 'markdown' else tr('새 PDF로 저장'))

    def reset_image_choice(self):
        self.replace_selection = (0, '')
        self.replace_choice.setText(tr('원본 이미지 선택'))

    def choose_original_image(self):
        if not self.source.text():
            self.status.setText(tr('PDF 파일을 먼저 선택해 주세요.'))
            return
        from .image_choice_ui import ImageChoiceDialog
        dialog = ImageChoiceDialog(self.source.text(), self.password.text(), self)
        if dialog.exec() == QDialog.Accepted:
            self.replace_selection = dialog.selected
            self.replace_choice.setText(tr('이미지 선택됨 · 다시 선택'))

    def choose_seal(self):
        from .seal_vault_ui import SealVaultDialog
        dialog = SealVaultDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.watermark_image.setText(dialog.selected_path)

    def choose_watermark(self):
        name, _ = QFileDialog.getOpenFileName(self, tr('이미지 선택'), '', tr('이미지 (*.png *.jpg *.jpeg)') if self.tool.currentData() in {'stamp', 'replace_image'} else 'PNG (*.png)')
        if name:
            self.watermark_image.setText(name)

    def choose(self):
        name, _ = QFileDialog.getOpenFileName(self, tr('PDF 선택'), '', 'PDF (*.pdf)')
        if name:
            self.source.setText(name)

    def start(self):
        from .license_ui import ensure_license
        if self.worker and self.worker.isRunning():
            return
        if not ensure_license(self):
            return
        if not self.source.text():
            self.status.setText(tr('PDF 파일을 먼저 선택해 주세요.'))
            return
        key = self.tool.currentData()
        if key == 'replace_image' and not self.replace_selection[0]:
            self.status.setText(tr('먼저 원본 이미지 선택 버튼으로 교체할 이미지를 선택해 주세요.'))
            return
        source = Path(self.source.text())
        form_review = None
        if key == 'auto_forms':
            from .form_review_ui import FormReviewDialog
            review = FormReviewDialog(source, self.password.text(), self)
            if review.exec() != QDialog.Accepted:
                return
            form_review = review.selection()
        extension = '.zip' if key in {'split_ranges', 'split_groups', 'split_toc', 'svg', 'dxf'} else '.md' if key == 'markdown' else '.pdf'
        target, _ = QFileDialog.getSaveFileName(self, tr('새 결과 저장'),
            str(source.with_name(source.stem + '_' + tr(TOOLS[key][0]) + extension)), f'{extension[1:].upper()} (*{extension})')
        if not target:
            return
        self.compare_pair = None
        self.compare_button.hide()
        self.pending_pair = (source, Path(target), self.password.text(),
                             self.user_password.text() if key == 'encrypt' else '') if extension == '.pdf' else None
        options = dict(source=str(source), target=target, operation=key, password=self.password.text(),
                       user_password=self.user_password.text(), owner_password=self.owner_password.text(),
                       allow_print=self.printing.isChecked(), allow_copy=self.copying.isChecked(),
                       watermark_text=self.watermark_text.text(), watermark_image=self.watermark_image.text(),
                       watermark_opacity=self.watermark_opacity.value(),
                       split_ranges=self.split_ranges.text(), group_size=self.group_size.value(), target_mb=self.target_mb.value(),
                       bates_prefix=self.bates_prefix.text(), bates_start=self.bates_start.value(),
                       bates_digits=self.bates_digits.value(), bates_hide_old=self.bates_hide_old.isChecked(),
                       bates_cover=self.bates_cover.isChecked(), stamp_pages=self.stamp_pages.text(),
                       stamp_x_mm=self.stamp_x.value(), stamp_y_mm=self.stamp_y.value(),
                       stamp_width_mm=self.stamp_width.value(), stamp_flatten=self.stamp_flatten.isChecked(),
                       replace_xref=self.replace_selection[0], replace_digest=self.replace_selection[1], form_review=form_review)
        self.worker = TransformWorker(options, self)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.result.connect(self.completed)
        self.worker.finished.connect(self.finished_job)
        for widget in (self.tool, self.pick, self.save, self.password, self.user_password, self.owner_password,
                       self.watermark_text, self.image_row, self.watermark_opacity, self.split_ranges, self.group_size,
                       self.target_mb, self.size_presets):
            widget.setEnabled(False)
        self.cancel.setText(tr('작업 취소'))
        self.status.setText(tr('내 PC에서 처리하고 있습니다.'))
        self.progress.setValue(0)
        self.worker.start()
        for field in (*self.bates_fields, *self.stamp_fields, self.replace_choice):
            field.setEnabled(False)

    def finished_job(self):
        for field in (self.password, self.user_password, self.owner_password):
            field.clear()
        for widget in (self.tool, self.pick, self.save, self.password):
            widget.setEnabled(True)
        self.changed()
        self.cancel.setText(tr('닫기'))
        self.compare_button.setEnabled(bool(self.compare_pair))

    def completed(self, success, message):
        self.status.setText(message)
        if success and self.pending_pair:
            self.compare_pair = self.pending_pair
            self.compare_button.setEnabled(False)
            self.compare_button.show()

    def compare_saved(self):
        if self.compare_pair:
            from .diff_ui import DiffDialog
            DiffDialog(self, *self.compare_pair).exec()

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.status.setText(tr('현재 처리가 끝나는 대로 취소합니다.'))
            return
        self.compare_pair = None
        self.pending_pair = None
        for field in (self.password, self.user_password, self.owner_password):
            field.clear()
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)


def show_tools(parent):
    AdvancedDialog(parent).exec()
