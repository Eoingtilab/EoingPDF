"""Unified Save As / Export, Draw Signature, and PDF Inspection dialogs."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from .action_icons import set_action_icon
from .localization import tr
from .sdk_theme import apply_style

EXPORT_FORMATS = (
    ('pdf', 'PDF 문서 (*.pdf)', '.pdf', '현재 편집 상태를 포함한 표준 PDF로 저장합니다.'),
    ('pdfa', '보관용 PDF/A (*.pdf)', '.pdf', '글꼴 정리와 스크립트 제거를 거친 장기 보관용 PDF로 저장합니다.'),
    ('png_zip', 'PNG 이미지 묶음 (*.zip)', '.zip', '각 페이지를 선명한 PNG 이미지로 만들어 ZIP으로 저장합니다.'),
    ('png', 'PNG 이미지 1장 (*.png)', '.png', '선택한 단일 페이지를 PNG 이미지 파일로 저장합니다.'),
    ('jpg_zip', 'JPG 이미지 묶음 (*.zip)', '.zip', '각 페이지를 JPG 이미지로 만들어 ZIP으로 저장합니다.'),
    ('jpg', 'JPG 이미지 1장 (*.jpg)', '.jpg', '선택한 단일 페이지를 JPG 이미지 파일로 저장합니다.'),
    ('long_png', '세로로 긴 PNG 한 장 (*.png)', '.png', '모든 페이지를 세로로 연결한 한 장의 PNG 이미지로 저장합니다.'),
    ('long_jpg', '세로로 긴 JPG 한 장 (*.jpg)', '.jpg', '모든 페이지를 세로로 연결한 한 장의 JPG 이미지로 저장합니다.'),
    ('txt', '텍스트 파일 (*.txt)', '.txt', '문서 텍스트를 추출합니다. 스캔은 Windows OCR을 사용합니다.'),
    ('md', 'Markdown 문서 (*.md)', '.md', '제목·본문·표를 Markdown 문서로 저장합니다.'),
    ('html', '웹 문서 HTML (*.html)', '.html', '브라우저에서 볼 수 있는 HTML 문서로 내보냅니다.'),
    ('json', 'JSON 구조 데이터 (*.json)', '.json', '페이지 텍스트와 메타데이터를 JSON으로 저장합니다.'),
    ('xml', 'XML 구조 데이터 (*.xml)', '.xml', '페이지 텍스트와 메타데이터를 XML로 저장합니다.'),
    ('svg', 'SVG 벡터 묶음 (*.zip)', '.zip', '페이지별 벡터 SVG 파일을 ZIP으로 저장합니다.'),
    ('dxf', 'DXF CAD 경로 묶음 (*.zip)', '.zip', '도형 경로를 CAD용 DXF 파일(ZIP)로 내보냅니다.'),
)


class _ExportWorker(QThread):
    progress = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, source, target, fmt, password, pages, dpi, quality):
        super().__init__()
        self.source = source
        self.target = target
        self.fmt = fmt
        self.password = password
        self.pages = pages
        self.dpi = dpi
        self.quality = quality

    def run(self):
        try:
            from .extra_tools import export_document
            export_document(
                self.source,
                self.target,
                self.fmt,
                password=self.password,
                pages=self.pages,
                dpi=self.dpi,
                quality=self.quality,
                cancelled=self.isInterruptionRequested,
                progress=self.progress.emit,
            )
            self.succeeded.emit(str(self.target))
        except Exception as error:
            self.failed.emit(str(error))


class SaveAsDialog(QDialog):
    """Save current document under a new filename or convert to another format."""

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.worker = None
        self.saved_path = None
        self._auto_filled_page = False
        self.setWindowTitle(tr('다른 이름으로 저장 · 형식 변환'))
        self.resize(540, 400)
        apply_style(self, 'QDialog {background:#f7f9fc;} QLineEdit, QComboBox, QSpinBox {background:white;border:1px solid #dae2f0;border-radius:6px;padding:6px;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel(tr('다른 파일명 또는 확장자로 저장'))
        heading.setStyleSheet('font-size:16px;font-weight:700;')
        layout.addWidget(heading)

        form = QFormLayout()
        self.format_combo = QComboBox()
        for key, label, _ext, _desc in EXPORT_FORMATS:
            self.format_combo.addItem(tr(label), key)
        form.addRow(tr('저장 형식'), self.format_combo)

        self.format_desc = QLabel()
        self.format_desc.setWordWrap(True)
        self.format_desc.setStyleSheet('color:#657187;font-size:12px;')
        form.addRow('', self.format_desc)

        base = getattr(viewer, 'original_path', None) or getattr(viewer, 'path', Path.home() / 'document.pdf')
        self.target_edit = QLineEdit(str(base.with_name(base.stem + '_사본.pdf')))
        browse_row = QHBoxLayout()
        browse_row.addWidget(self.target_edit, 1)
        browse_btn = QPushButton(tr('찾아보기'))
        browse_btn.clicked.connect(self.choose_target)
        browse_row.addWidget(browse_btn)
        form.addRow(tr('저장 경로'), browse_row)

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText(tr('비우면 전체 페이지 · 예: 1-3, 5'))
        self.pages_edit.textEdited.connect(lambda _text: setattr(self, '_auto_filled_page', False))
        form.addRow(tr('페이지 범위'), self.pages_edit)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 300)
        self.dpi_spin.setValue(150)
        self.dpi_spin.setSuffix(' DPI')
        form.addRow(tr('이미지 해상도'), self.dpi_spin)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(40, 100)
        self.quality_spin.setValue(90)
        self.quality_spin.setSuffix('%')
        form.addRow(tr('JPG 품질'), self.quality_spin)

        layout.addLayout(form)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        layout.addWidget(self.progress)

        self.status = QLabel(tr('원본 파일은 변경하지 않고 새 파일로 저장합니다.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.open_folder_btn = QPushButton(tr('결과 폴더 열기'))
        self.open_folder_btn.hide()
        self.open_folder_btn.clicked.connect(self.open_folder)
        buttons.addWidget(self.open_folder_btn)
        buttons.addStretch(1)
        self.save_btn = QPushButton(tr('저장하기'))
        set_action_icon(self.save_btn, 'save')
        self.save_btn.setObjectName('primary')
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.start_export)
        buttons.addWidget(self.save_btn)
        self.close_btn = QPushButton(tr('닫기'))
        self.close_btn.clicked.connect(self.reject)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)

        self.format_combo.currentIndexChanged.connect(self._sync_format)
        self._sync_format()

    def _selected_spec(self):
        key = self.format_combo.currentData()
        return next(item for item in EXPORT_FORMATS if item[0] == key)

    def _sync_format(self):
        key, _label, ext, desc = self._selected_spec()
        self.format_desc.setText(tr(desc))
        is_image = key in {'png_zip', 'png', 'jpg_zip', 'jpg', 'long_png', 'long_jpg'}
        is_jpg = 'jpg' in key
        self.dpi_spin.setEnabled(is_image)
        self.quality_spin.setEnabled(is_jpg)
        if key in {'png', 'jpg'} and not self.pages_edit.text().strip() and getattr(self.viewer, 'page', None):
            self.pages_edit.setText(str(self.viewer.page.value()))
            self._auto_filled_page = True
        elif key not in {'png', 'jpg'} and self._auto_filled_page:
            self.pages_edit.clear()
            self._auto_filled_page = False
        current = Path(self.target_edit.text().strip() or 'document')
        base = getattr(self.viewer, 'original_path', None) or Path.home() / 'document.pdf'
        stem = current.stem if current.stem else base.stem
        if stem == base.stem and ext == '.pdf':
            stem = base.stem + '_사본'
        parent = current.parent if str(current.parent) != '.' else base.parent
        self.target_edit.setText(str(parent / f'{stem}{ext}'))

    def choose_target(self):
        _key, label, ext, _desc = self._selected_spec()
        path, _ = QFileDialog.getSaveFileName(self, tr('다른 이름으로 저장'), self.target_edit.text(), tr(label))
        if path:
            target = Path(path)
            if target.suffix.lower() != ext:
                target = target.with_suffix(ext)
            self.target_edit.setText(str(target))

    def start_export(self):
        if self.worker and self.worker.isRunning():
            return
        if not getattr(self.viewer, 'path', None):
            self.status.setText(tr('열려 있는 문서가 없습니다.'))
            return
        key, _label, ext, _desc = self._selected_spec()
        raw_target = self.target_edit.text().strip()
        if not raw_target:
            self.status.setText(tr('저장할 파일 경로를 입력해 주세요.'))
            return
        target = Path(raw_target)
        if target.suffix.lower() != ext:
            target = target.with_suffix(ext)
            self.target_edit.setText(str(target))
        if target.exists():
            answer = QMessageBox.question(
                self,
                tr('파일 덮어쓰기 확인'),
                tr('이미 같은 이름의 파일이 있습니다. 새 이름으로 저장할까요? (원본 보호를 위해 기존 파일과 같은 경로는 덮어쓰지 않습니다)'),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
            # Resolve non-destructive target name when existing file collides.
            target = _next_available_path(target)
            self.target_edit.setText(str(target))
        try:
            source = self.viewer.stage_current_preview(display=False)
        except Exception as error:
            self.status.setText(str(error))
            return
        pages = self.pages_edit.text().strip()
        if key in {'png', 'jpg'} and not pages:
            pages = str(self.viewer.page.value())
        target.parent.mkdir(parents=True, exist_ok=True)
        self.save_btn.setEnabled(False)
        self.status.setText(tr('저장하고 있습니다…'))
        self.progress.setValue(0)
        self.worker = _ExportWorker(
            source, target, key, getattr(self.viewer, 'password', ''),
            pages, self.dpi_spin.value(), self.quality_spin.value(),
        )
        self.worker.progress.connect(self.progress.setValue)
        self.worker.succeeded.connect(self._on_succeeded)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_succeeded(self, saved):
        self.save_btn.setEnabled(True)
        self.saved_path = Path(saved)
        self.progress.setValue(100)
        self.status.setText(tr('저장했어요: {file}', file=self.saved_path.name))
        self.open_folder_btn.show()
        if self.saved_path.suffix.lower() == '.pdf' and hasattr(self.viewer, 'add_to_library'):
            self.viewer.add_to_library([str(self.saved_path)])

    def _on_failed(self, message):
        self.save_btn.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText(message)

    def open_folder(self):
        if self.saved_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.saved_path.parent)))

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(2000)
        super().reject()


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10000):
        candidate = path.with_name(f'{path.stem} ({index}){path.suffix}')
        if not candidate.exists():
            return candidate
    raise ValueError(tr('사용 가능한 저장 파일명을 찾지 못했습니다.'))


class _SignaturePad(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.strokes: list[tuple[list[QPointF], QColor, int]] = []
        self.current: list[QPointF] = []
        self.pen_color = QColor('#111827')
        self.pen_width = 4
        self.setMinimumSize(420, 190)
        self.setCursor(Qt.CrossCursor)

    def clear(self):
        self.strokes.clear()
        self.current = []
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.current = [event.position()]
            self.strokes.append((self.current, QColor(self.pen_color), self.pen_width))
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.current:
            self.current.append(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.current = []

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#ffffff'))
        painter.setPen(QPen(QColor('#dce3f0'), 1, Qt.DashLine))
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        for points, color, width in self.strokes:
            if len(points) < 2:
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(points[0], width / 2, width / 2)
                continue
            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            painter.drawPath(path)

    def to_png_bytes(self) -> bytes:
        if not self.strokes:
            raise ValueError(tr('먼저 서명을 그려 주세요.'))
        scale = 2
        image = QImage(self.width() * scale, self.height() * scale, QImage.Format_RGBA8888)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(scale, scale)
        for points, color, width in self.strokes:
            if len(points) < 2:
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(points[0], width / 2, width / 2)
                continue
            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            painter.drawPath(path)
        painter.end()
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        image.save(buf, 'PNG')
        return bytes(buf.data())


class SignDrawDialog(QDialog):
    """Create a drawn or typed transparent signature/seal and place it immediately."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result_png_path: Path | None = None
        self._temp_dir = None
        self.setWindowTitle(tr('서명 그리기 · 도장 만들기'))
        self.resize(500, 390)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # Tab 1: Freehand Draw
        draw_tab = QWidget()
        draw_layout = QVBoxLayout(draw_tab)
        self.pad = _SignaturePad()
        draw_layout.addWidget(self.pad, 1)
        controls = QHBoxLayout()
        self.color_combo = QComboBox()
        for label, color in ((tr('검정'), '#111827'), (tr('진파랑'), '#1d4ed8'), (tr('도장 빨강'), '#c81e1e')):
            self.color_combo.addItem(label, color)
        self.color_combo.currentIndexChanged.connect(
            lambda: setattr(self.pad, 'pen_color', QColor(self.color_combo.currentData()))
        )
        controls.addWidget(QLabel(tr('색상')))
        controls.addWidget(self.color_combo)
        clear_btn = QPushButton(tr('지우기'))
        clear_btn.clicked.connect(self.pad.clear)
        controls.addWidget(clear_btn)
        controls.addStretch(1)
        draw_layout.addLayout(controls)
        self.tabs.addTab(draw_tab, tr('직접 그리기'))

        # Tab 2: Typed Signature / Seal
        type_tab = QWidget()
        type_layout = QFormLayout(type_tab)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr('예: 홍길동 · 어잉티연구소'))
        type_layout.addRow(tr('서명/도장 문구'), self.name_edit)
        self.style_combo = QComboBox()
        self.style_combo.addItem(tr('빨간 원형 도장'), 'circle-red')
        self.style_combo.addItem(tr('빨간 사각 직인'), 'box-red')
        self.style_combo.addItem(tr('검정 필기 서명'), 'text-black')
        self.style_combo.addItem(tr('파랑 필기 서명'), 'text-blue')
        type_layout.addRow(tr('모양'), self.style_combo)
        self.tabs.addTab(type_tab, tr('글자로 만들기'))

        layout.addWidget(self.tabs, 1)
        self.save_vault_check = QCheckBox(tr('도장 보관함에도 함께 저장하기'))
        layout.addWidget(self.save_vault_check)

        row = QHBoxLayout()
        row.addStretch(1)
        place_btn = QPushButton(tr('문서에 바로 배치'))
        set_action_icon(place_btn, 'stamp')
        place_btn.setObjectName('primary')
        place_btn.clicked.connect(self.accept_signature)
        row.addWidget(place_btn)
        cancel_btn = QPushButton(tr('취소'))
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)
        layout.addLayout(row)

    def _render_typed_png(self) -> bytes:
        text = self.name_edit.text().strip()
        if not text:
            raise ValueError(tr('서명 또는 도장에 넣을 글자를 입력해 주세요.'))
        style = self.style_combo.currentData()
        is_seal = style in ('circle-red', 'box-red')
        w, h = (220, 220) if is_seal else (420, 180)
        image = QImage(w, h, QImage.Format_RGBA8888)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            if is_seal:
                painter.setPen(QPen(QColor('#c81e1e'), 8))
                if style == 'circle-red':
                    painter.drawEllipse(QRectF(12, 12, 196, 196))
                else:
                    painter.drawRoundedRect(QRectF(12, 12, 196, 196), 12, 12)
                painter.setFont(QFont('Pretendard', 28, QFont.Bold))
                painter.drawText(QRectF(20, 20, 180, 180), Qt.AlignCenter | Qt.TextWordWrap, text)
            else:
                color = '#1d4ed8' if style == 'text-blue' else '#111827'
                painter.setPen(QColor(color))
                font = QFont('Pretendard', 40, QFont.DemiBold)
                font.setItalic(True)
                painter.setFont(font)
                painter.drawText(image.rect().adjusted(10, 10, -10, -10), Qt.AlignCenter, text)
        finally:
            painter.end()
        from PIL import Image as PilImage
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        image.save(buf, 'PNG')
        with PilImage.open(io.BytesIO(bytes(buf.data()))) as pil:
            box = pil.getchannel('A').getbbox()
            if box:
                pil = pil.crop(box)
            out = io.BytesIO()
            pil.save(out, format='PNG')
            return out.getvalue()

    def accept_signature(self):
        try:
            raw = self.pad.to_png_bytes() if self.tabs.currentIndex() == 0 else self._render_typed_png()
            self._temp_dir = tempfile.TemporaryDirectory(prefix='eoing-sign-')
            png_path = Path(self._temp_dir.name) / 'signature.png'
            png_path.write_bytes(raw)
            if self.save_vault_check.isChecked():
                from .seal_vault import save_seal
                title = (self.name_edit.text().strip() or tr('직접 그린 서명'))[:40]
                save_seal(title, png_path)
            self.result_png_path = png_path
            self.accept()
        except Exception as error:
            QMessageBox.warning(self, tr('서명 생성 실패'), str(error))


class PdfInfoDialog(QDialog):
    """Display comprehensive PDF structure, fonts, permissions, and safety diagnostics."""

    def __init__(self, path, password='', parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('PDF 상세 정보 · 규격 검사'))
        self.resize(560, 480)
        layout = QVBoxLayout(self)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        layout.addWidget(view, 1)
        try:
            from .extra_tools import inspect_pdf_report
            info = inspect_pdf_report(path, password)
            mb = info['file_size_bytes'] / 1048576
            lines = [
                f"{tr('파일명')}: {info['file_name']}",
                f"{tr('크기')}: {mb:.2f} MB ({info['file_size_bytes']:,} bytes)",
                f"{tr('페이지 수')}: {info['page_count']}",
                f"{tr('PDF 버전')}: {info['pdf_version'] or '-'}",
                f"{tr('암호화')}: {tr('예') if info['encrypted'] else tr('아니오')}",
                f"{tr('양식 포함')}: {tr('예') if info['has_forms'] else tr('아니오')}",
                f"{tr('주석 수')}: {info['annotation_count']}",
                f"{tr('이미지 수')}: {info['image_count']}",
                f"{tr('첨부 파일 수')}: {info['attachment_count']}",
                f"{tr('JavaScript/실행 액션')}: {tr('포함됨 (보안 소독 권장)') if info['has_javascript'] else tr('없음')}",
                f"{tr('페이지 규격')}: {', '.join(info['page_sizes'])} {'(' + tr('규격 혼재') + ')' if info['mixed_page_sizes'] else ''}",
                '',
                f"[{tr('권한')}] " + tr('인쇄={print_ok} · 복사={copy_ok} · 수정={modify_ok} · 주석={annotate_ok}',
                                         print_ok=info['permissions']['print'], copy_ok=info['permissions']['copy'],
                                         modify_ok=info['permissions']['modify'], annotate_ok=info['permissions']['annotate']),
                '',
                f"[{tr('사용 글꼴')} ({len(info['fonts'])})]",
                *(f'- {name}' for name in info['fonts'][:15]),
            ]
            if info['unembedded_fonts']:
                lines += ['', f"[{tr('임베드되지 않은 글꼴 경고')}]", *(f'! {name}' for name in info['unembedded_fonts'])]
            if info['metadata']:
                lines += ['', f"[{tr('문서 메타데이터')}]", *(f'- {k}: {v}' for k, v in info['metadata'].items())]
            view.setPlainText('\n'.join(lines))
        except Exception as error:
            view.setPlainText(str(error))
        close_btn = QPushButton(tr('닫기'))
        set_action_icon(close_btn, 'close')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class ShortcutsDialog(QDialog):
    """Comprehensive quick-reference dialog listing all viewer, editing, and presentation shortcuts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('단축키 안내 · 어잉PDF'))
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        head = QLabel(tr('자주 쓰는 단축키로 PDF 보기·편집·발표를 빠르게 전환할 수 있습니다.'))
        head.setWordWrap(True)
        layout.addWidget(head)

        groups = (
            (tr('파일 · 저장'), (
                ('Ctrl+O', tr('PDF 열기')),
                ('Ctrl+S', tr('사본 저장 (원본 보존)')),
                ('Ctrl+Shift+S', tr('다른 이름으로 저장 · 15종 형식 내보내기')),
                ('Ctrl+P', tr('인쇄 준비 메뉴 열기')),
                ('Ctrl+I', tr('PDF 상세 정보 · 규격 검사')),
                ('Ctrl+W', tr('현재 문서 창 닫기')),
            )),
            (tr('보기 · 화면 전환'), (
                ('F5 / Shift+F5', tr('현재 페이지부터 슬라이드쇼 시작')),
                ('Ctrl+B', tr('왼쪽 사이드바(페이지·보관함) 표시/숨기기')),
                ('Ctrl+J', tr('오른쪽 PDF 도구 패널 표시/숨기기')),
                ('Ctrl++ / Ctrl+-', tr('화면 확대 / 축소')),
                ('Ctrl+0 / Ctrl+1 / Ctrl+2', tr('100% / 너비 맞춤 / 페이지 맞춤')),
                ('PgUp / PgDown / Home / End', tr('이전 / 다음 / 첫 / 마지막 페이지')),
            )),
            (tr('편집 · 도구 · 검색'), (
                ('Ctrl+K / Ctrl+Shift+T', tr('65+ PDF 도구 검색 및 열기')),
                ('Ctrl+M', tr('페이지 멀티툴 편집기 전환')),
                ('Ctrl+D', tr('서명 직접 그리기 (투명 PNG 도장)')),
                ('Ctrl+F', tr('폴더 내 문서 내용 검색')),
                ('Ctrl+R / Ctrl+Shift+R', tr('현재 문서 시계 / 반시계 90° 회전')),
                ('Ctrl+Z / Ctrl+Y', tr('실행 취소 / 다시 실행')),
                ('F1', tr('단축키 안내 열기')),
            )),
        )

        lines = []
        for group_title, pairs in groups:
            lines.append(f'■ {group_title}')
            for shortcut, desc in pairs:
                lines.append(f'  {shortcut:<24}  {desc}')
            lines.append('')

        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText('\n'.join(lines).strip())
        layout.addWidget(viewer, 1)

        close_btn = QPushButton(tr('닫기'))
        set_action_icon(close_btn, 'close')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)
        apply_style(
            self,
            'QDialog {background:#ffffff;} QPlainTextEdit {background:#f7f9fc;border:1px solid #dae2f0;border-radius:8px;padding:10px;font-size:13px;}',
        )
