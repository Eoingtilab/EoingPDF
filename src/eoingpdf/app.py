import argparse
import logging
import sys
from pathlib import Path

import pymupdf as pdf
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QSize, QStandardPaths
from PySide6.QtGui import QFont, QFontDatabase, QPixmap, QImage, QDesktopServices, QIcon, QPainter, QColor, QPen
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QFileDialog,
    QLineEdit, QComboBox, QProgressBar, QMessageBox, QAbstractItemView, QScrollArea)

from .core import Request, run, IMAGES, Cancelled
from .convert import SUPPORTED
from .sdk_theme import adapt_style
from .localization import tr

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
TOOLS = [
    ('merge', '문서 합치기', '다양한 문서를 하나의 PDF로.', 'PDF · 이미지 · Office · 한글 · 텍스트를 목록 순서대로 합칩니다.', '합친 PDF 저장'),
    ('extract', '페이지 정리', '필요한 페이지만 골라 새로운 문서로.', '페이지 범위로 추출 · 삭제 · 순서 변경을 한 번에.', '선택한 페이지 저장'),
    ('rotate', '페이지 회전', '방향이 다른 페이지를 바로잡으세요.', '선택한 페이지만 시계 방향으로 회전합니다.', '회전한 PDF 저장'),
    ('optimize', '용량 최적화', '문서의 품질은 그대로, 불필요한 용량은 덜어내요.', '화질을 낮추지 않는 최적화입니다. 용량이 줄지 않을 수도 있어요.', '최적화한 PDF 저장'),
    ('convert', 'PDF로 변환', '문서와 이미지를 빠르게 PDF로.', 'Office·한글 변환 실패 시 설치된 LibreOffice로 다시 시도합니다. 형식에 따라 지원이 다릅니다.', '각각 PDF로 저장'),
    ('png', 'PDF → 이미지', '필요한 페이지를 선명한 PNG 이미지로.', '선택한 페이지를 PNG로 변환해 ZIP에 담습니다.', '이미지 ZIP 저장'),
    ('text', '텍스트 추출', '문서 속 글자만 빠르게 꺼내세요.', '스캔 페이지는 Windows OCR로 읽습니다. OCR 인식 결과는 확인해 주세요.', '텍스트 파일 저장'),
    ('number', '페이지 번호', '제출 전에 페이지 번호까지 정돈하세요.', '페이지 하단 중앙에 번호를 추가합니다. 기존 내용과 겹치는지 확인하세요.', '번호를 넣어 저장'),
    ('summary', '핵심문장 요약', '긴 문서에서 중요한 문장만 빠르게.', '외부 전송 없는 문장 발췌 요약입니다. 출처 페이지를 함께 기록합니다.', '요약 저장'),
]

STYLE = adapt_style('''
QWidget { font-family: 'Pretendard'; font-size: 14px; color: #263246; }
QMainWindow, QDialog, QWidget#workspace { background: #f7f9fc; }
QMessageBox { background: #ffffff; }
QFrame#sidebar { background: #ffffff; border-right: 1px solid #e7ecf3; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 23px; font-weight: 700; color: #192b49; }
QLabel#eyebrow { font-size: 11px; font-weight: 600; color: #95a0b3; }
QLabel#title { font-size: 30px; font-weight: 700; letter-spacing: -1px; color: #172a47; }
QLabel#subtitle { color: #778398; font-size: 14px; }
QLabel#badge { background: #ecf6f2; color: #458475; border-radius: 12px; padding: 6px 12px; font-size: 11px; }
QLabel#section { font-weight: 600; font-size: 15px; }
QLabel#small { font-size: 12px; color: #8994a6; }
QPushButton { background: #fff; border: 1px solid #e2e7ef; border-radius: 12px; padding: 9px 13px; font-weight: 500; }
QPushButton:hover { background: #f1f5fb; border-color: #c6d3e6; }
QPushButton:focus { border: 2px solid #7c9dfa; }
QPushButton:disabled { color: #a5adba; background: #eef1f6; border-color: #e7ebf2; }
QPushButton#nav { text-align: left; border: none; padding: 13px 14px; color: #657187; border-radius: 9px; }
QPushButton#nav:checked { background: #edf2ff; color: #416ae6; font-weight: 600; }
QPushButton#nav:hover { background: #f4f6fb; }
QPushButton#primary { background: #4b70ed; border: none; color: white; padding: 13px 20px; font-weight: 600; }
QPushButton#primary:hover { background: #3e61d8; }
QPushButton#primary:disabled { background: #c5d0f3; color: #fff; }
QFrame#panel { background: white; border: 1px solid #e4eaf3; border-radius: 20px; }
QFrame#drop { background: #f9fbff; border: 1px dashed #b9cbed; border-radius: 11px; }
QLabel#upload { font-size: 35px; color: #5578df; }
QListWidget { background: white; border: none; outline: none; }
QListWidget::item { border-bottom: 1px solid #f0f3f8; padding: 11px 6px; border-radius: 6px; }
QListWidget::item:selected { background: #eff3ff; color: #375dcc; }
QListWidget::item:hover { background: #f6f8fc; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #f9fbfd; border: 1px solid #e1e7f0; border-radius: 7px; padding: 9px; }
QComboBox QAbstractItemView { background: #ffffff; color: #263246; selection-background-color: #edf2ff; selection-color: #183b8f; }
QLineEdit:focus { border-color: #6989ef; }
QProgressBar { border: none; background: #e8edf7; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: #6385ed; border-radius: 3px; }
QLabel#preview { background: #f1f4f9; border-radius: 9px; color: #94a0b3; }
QToolTip { background: #25354b; color: white; border: none; padding: 6px; }
''')


def label(text, name='', wrap=False):
    obj = QLabel(tr(text))
    obj.setObjectName(name)
    obj.setWordWrap(wrap)
    return obj


def button(text, callback, name=''):
    obj = QPushButton(tr(text))
    obj.setMinimumHeight(40)
    obj.setObjectName(name)
    obj.setCursor(Qt.PointingHandCursor)
    obj.clicked.connect(callback)
    return obj


def icon(index):
    pix = QPixmap(24, 24)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#7487aa'), 1.5))
    if index in (0, 4):
        painter.drawRoundedRect(4, 3, 12, 15, 2, 2)
        painter.drawRoundedRect(8, 7, 12, 15, 2, 2)
    elif index == 2:
        painter.drawArc(4, 4, 16, 16, 30 * 16, 290 * 16)
        painter.drawLine(19, 3, 20, 10)
        painter.drawLine(14, 9, 20, 10)
    else:
        painter.drawRoundedRect(5, 3, 14, 18, 2, 2)
        for y in (8, 12, 16):
            painter.drawLine(9, y, 15, y)
    painter.end()
    return QIcon(pix)


class Worker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(str)
    failed = Signal(str)
    batch_done = Signal(dict)

    def __init__(self, request):
        super().__init__()
        self.request = request

    def run(self):
        try:
            if self.request.tool in {'merge', 'convert', 'summary'}:
                from .jobs import execute
                result = execute(self.request.tool, self.request.files, self.request.folder, self.progress.emit, self.isInterruptionRequested)
                self.batch_done.emit(result)
                return
            output = run(self.request, self.progress.emit, self.isInterruptionRequested)
            self.succeeded.emit(str(output))
        except Cancelled as error:
            self.failed.emit(str(error))
        except ValueError as error:
            self.failed.emit(str(error))
        except Exception:
            logging.exception(tr('PDF 작업 실패'))
            self.failed.emit(tr('파일을 처리하지 못했습니다. 파일 손상, 저장 공간과 폴더 권한을 확인해 주세요.'))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tool = 'merge'
        self.worker = None
        self.preview_page = 0
        self.last_output = None
        self.setWindowTitle(tr('어잉PDF · EoingPDF'))
        self.resize(1180, 800)
        self.setMinimumSize(1040, 740)
        self.setAcceptDrops(True)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        side = QFrame()
        side.setObjectName('sidebar')
        side.setMinimumWidth(180)
        nav = QVBoxLayout(side)
        nav.setContentsMargins(19, 29, 19, 22)
        nav.addWidget(label(tr('어잉PDF'), 'brand'))
        nav.addWidget(label(tr('작게, 가볍게, 완벽하게.'), 'small'))
        nav.addSpacing(38)
        nav.addWidget(label(tr('  PDF 도구'), 'eyebrow'))
        nav.addSpacing(9)
        self.nav_buttons = []
        for i, (key, title, *_) in enumerate(TOOLS):
            b = button(title, lambda checked=False, k=key: self.select_tool(k), 'nav')
            b.setCheckable(True)
            b.setIcon(icon(i))
            b.setIconSize(QSize(22, 22))
            nav.addWidget(b)
            self.nav_buttons.append(b)
        nav.addStretch()
        nav.addWidget(button(tr('PDF 열어보기'), self.choose_reader))
        from .staging_dock import show_dock
        nav.addWidget(button(tr('작은 창에 파일 모으기'), lambda: show_dock(self)))
        from .advanced_ui import show_tools
        nav.addWidget(button(tr('암호·보조 도구'), lambda: show_tools(self)))
        from .diff_ui import show_diff
        nav.addWidget(button(tr('두 문서 비교'), lambda: show_diff(self)))
        nav.addWidget(button(tr('문서 내용 검색'), self.open_search))
        from .settings_ui import SettingsDialog
        nav.addWidget(button(tr('설정 · 라이선스 · 업데이트'),
                             lambda: SettingsDialog(self, self.menu_settings).exec()))
        nav.addWidget(button(tr('사용 안내'), self.help))
        nav.addSpacing(16)
        nav.addWidget(label(tr('어잉티연구소'), 'eyebrow'))
        side_scroll = QScrollArea()
        side_scroll.setFixedWidth(210)
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setWidget(side)
        shell.addWidget(side_scroll)

        workspace = QWidget()
        workspace.setObjectName('workspace')
        main = QVBoxLayout(workspace)
        main.setContentsMargins(32, 27, 32, 23)
        main.setSpacing(16)
        top = QHBoxLayout()
        top.addWidget(label(tr('내 문서를 위한 작은 작업실'), 'small'))
        top.addStretch()
        top.addWidget(label(tr('●  내 PC에서 안전하게'), 'badge'))
        main.addLayout(top)
        from .capture_ui import CaptureChip
        self.capture_chip = CaptureChip(self)
        main.addWidget(self.capture_chip)
        main.addSpacing(7)
        self.title = label('', 'title')
        self.subtitle = label('', 'subtitle')
        main.addWidget(self.title)
        main.addWidget(self.subtitle)
        main.addSpacing(6)

        middle = QHBoxLayout()
        middle.setSpacing(18)
        self.editor = QFrame()
        self.editor.setObjectName('panel')
        edit = QVBoxLayout(self.editor)
        edit.setContentsMargins(20, 20, 20, 20)
        edit.setSpacing(12)
        files_header = QHBoxLayout()
        files_header.addWidget(label(tr('01   파일 담기'), 'section'))
        files_header.addStretch()
        self.count_label = label(tr('0개 파일'), 'small')
        files_header.addWidget(self.count_label)
        edit.addLayout(files_header)
        drop = QFrame()
        drop.setObjectName('drop')
        dl = QVBoxLayout(drop)
        dl.setContentsMargins(12, 16, 12, 16)
        for text, name in [('↑', 'upload'), (tr('여기에 파일을 놓아주세요'), 'section')]:
            item = label(text, name)
            item.setAlignment(Qt.AlignCenter)
            dl.addWidget(item)
        self.accept_label = label(tr('PDF 파일 · 여러 개도 한 번에'), 'small')
        self.accept_label.setAlignment(Qt.AlignCenter)
        dl.addWidget(self.accept_label)
        add = button(tr('＋  파일 선택'), self.choose_files)
        add.setObjectName('chooseFiles')
        dl.addWidget(add, 0, Qt.AlignHCenter)
        edit.addWidget(drop)
        self.files = QListWidget()
        self.files.setMinimumHeight(90)
        self.files.setDragDropMode(QAbstractItemView.InternalMove)
        self.files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.files.currentRowChanged.connect(self.reset_preview)
        self.files.model().rowsMoved.connect(lambda *args: self.update_count())
        edit.addWidget(self.files, 1)
        row = QHBoxLayout()
        row.addWidget(button('↑', lambda: self.move_file(-1)))
        row.addWidget(button('↓', lambda: self.move_file(1)))
        row.addStretch()
        row.addWidget(button(tr('선택 제거'), self.remove_file))
        row.addWidget(button(tr('비우기'), self.clear_files))
        edit.addLayout(row)
        self.option_hint = label('', 'small', True)
        edit.addWidget(self.option_hint)
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText(tr('전체 페이지 · 예: 1-3, 5, 8-6'))
        self.page_input.setAccessibleName(tr('작업할 페이지 범위'))
        self.page_input.setToolTip(tr('빈칸은 전체 페이지입니다. 입력 순서대로 추출하며 중복도 허용합니다.'))
        edit.addWidget(self.page_input)
        self.rotation = QComboBox()
        self.rotation.addItems([tr('시계 방향 90°'), '180°', tr('시계 방향 270°')])
        edit.addWidget(self.rotation)
        middle.addWidget(self.editor, 3)

        preview_box = QFrame()
        preview_box.setObjectName('panel')
        preview_box.setFixedWidth(268)
        pr = QVBoxLayout(preview_box)
        pr.setContentsMargins(16, 20, 16, 20)
        pr.addWidget(label(tr('미리보기'), 'section'))
        pr.addWidget(label(tr('선택한 원본 페이지'), 'small'))
        pr.addSpacing(12)
        self.preview = label(tr('문서를 담으면\n이곳에 미리보기가 나타나요'), 'preview')
        self.preview.setFixedSize(234, 270)
        self.preview.setAlignment(Qt.AlignCenter)
        pr.addWidget(self.preview)
        controls = QHBoxLayout()
        self.prev_button = button('‹', lambda: self.change_page(-1))
        self.next_button = button('›', lambda: self.change_page(1))
        self.page_label = label('— / —', 'small')
        self.page_label.setAlignment(Qt.AlignCenter)
        controls.addWidget(self.prev_button)
        controls.addWidget(self.page_label, 1)
        controls.addWidget(self.next_button)
        pr.addLayout(controls)
        pr.addWidget(button(tr('PDF 크게 보기'), self.open_reader))
        self.file_info = label(tr('아직 선택한 파일이 없어요.'), 'small', True)
        pr.addWidget(self.file_info)
        pr.addStretch()
        pr.addWidget(label(tr('안심하고 작업하세요'), 'section'))
        pr.addWidget(label(tr('원본은 그대로 보관하고,\n결과는 새 파일로 저장합니다.'), 'small', True))
        middle.addWidget(preview_box)
        main.addLayout(middle, 1)

        output_row = QHBoxLayout()
        output_row.addWidget(label(tr('02   저장 위치'), 'section'))
        self.folder = QLineEdit(str(Path(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)) / 'EoingPDF'))
        self.folder.setAccessibleName(tr('결과 저장 폴더'))
        output_row.addWidget(self.folder, 1)
        self.folder_button = button(tr('변경'), self.choose_folder)
        output_row.addWidget(self.folder_button)
        main.addLayout(output_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        main.addWidget(self.progress)
        bottom = QHBoxLayout()
        self.status = label(tr('파일을 담고, 원하는 결과를 만드세요.'), 'small', True)
        bottom.addWidget(self.status, 1)
        self.open_button = button(tr('결과 열기 ↗'), self.open_result)
        self.open_button.hide()
        bottom.addWidget(self.open_button)
        self.cancel_button = button(tr('취소'), self.cancel)
        self.cancel_button.hide()
        bottom.addWidget(self.cancel_button)
        self.run_button = button('', self.start, 'primary')
        bottom.addWidget(self.run_button)
        main.addLayout(bottom)
        workspace.setMinimumHeight(800)
        workspace_scroll = QScrollArea()
        workspace_scroll.setWidgetResizable(True)
        workspace_scroll.setFrameShape(QFrame.NoFrame)
        workspace_scroll.setWidget(workspace)
        shell.addWidget(workspace_scroll, 1)
        self.select_tool('merge')

    def select_tool(self, key):
        if self.busy():
            return
        if self.tool in {'merge', 'convert', 'summary'} and key not in {'merge', 'convert', 'summary'}:
            self.files.clear()
        self.tool = key
        for b, entry in zip(self.nav_buttons, TOOLS):
            b.setChecked(entry[0] == key)
        entry = next(t for t in TOOLS if t[0] == key)
        self.title.setText(tr(entry[1]))
        self.subtitle.setText(tr(entry[2]))
        self.option_hint.setText(tr(entry[3]))
        self.run_button.setText(tr(entry[4]))
        self.page_input.setVisible(key not in {'merge', 'convert', 'summary', 'optimize'})
        self.rotation.setVisible(key == 'rotate')
        self.accept_label.setText(tr('PDF · 이미지 · Office · 한글 · 텍스트' if key in {'merge', 'convert', 'summary'} else 'PDF 파일 · 로컬에서 안전하게'))
        self.update_count()

    def busy(self):
        return self.worker is not None

    def update_count(self):
        count = self.files.count()
        self.count_label.setText(tr('{count}개 파일', count=count))
        self.run_button.setEnabled(count > 0 and not self.busy())
        if not self.busy():
            self.status.setText(tr('목록의 모든 파일을 처리합니다.' if self.tool in {'merge', 'convert', 'summary'} else '목록에서 선택한 파일 한 개를 처리합니다.'))

    def choose_files(self):
        kind = tr('지원 문서 (') + ' '.join('*' + ext for ext in sorted(SUPPORTED)) + ')' if self.tool in {'merge', 'convert', 'summary'} else 'PDF (*.pdf)'
        paths, _ = QFileDialog.getOpenFileNames(self, tr('파일 담기'), '', kind)
        self.add_files(paths)

    def add_files(self, paths):
        if self.busy():
            return
        rejected = []
        known = {self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())}
        for raw in paths:
            path = Path(raw).resolve()
            allowed = SUPPORTED if self.tool in {'merge', 'convert', 'summary'} else {'.pdf'}
            if not path.is_file() or path.suffix.lower() not in allowed:
                rejected.append(path.name)
                continue
            if str(path) in known:
                continue
            try:
                size = path.stat().st_size / 1024 / 1024
            except OSError:
                rejected.append(path.name)
                continue
            item = QListWidgetItem(f'{path.name}\n{size:.2f} MB')
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(str(path))
            self.files.addItem(item)
            known.add(str(path))
        if self.files.currentRow() < 0 and self.files.count():
            self.files.setCurrentRow(0)
        self.update_count()
        if rejected:
            self.status.setText(tr('지원하지 않거나 읽을 수 없는 파일 {v0}개를 제외했습니다.', v0=len(rejected)))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def move_file(self, delta):
        row = self.files.currentRow()
        target = row + delta
        if 0 <= row < self.files.count() and 0 <= target < self.files.count():
            item = self.files.takeItem(row)
            self.files.insertItem(target, item)
            self.files.setCurrentRow(target)

    def remove_file(self):
        if self.files.currentRow() >= 0:
            self.files.takeItem(self.files.currentRow())
        self.update_count()
        self.reset_preview()

    def clear_files(self):
        self.files.clear()
        self.update_count()
        self.reset_preview()

    def reset_preview(self, *_):
        self.preview_page = 0
        self.render_preview()

    def choose_reader(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('PDF 열기'), '', 'PDF (*.pdf)')
        if path:
            from .viewer import PdfViewer, PdfOpenCancelled
            try:
                self.reader = PdfViewer(path, self)
                self.reader.show()
            except PdfOpenCancelled:
                return
            except Exception as error:
                QMessageBox.warning(self, tr('PDF 열기 실패'), str(error))

    def open_reader(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        item = self.files.currentItem()
        if item is None or Path(item.data(Qt.UserRole)).suffix.lower() != '.pdf':
            self.status.setText(tr('열어볼 PDF를 목록에서 선택해 주세요.'))
            return
        from .viewer import PdfViewer, PdfOpenCancelled
        try:
            self.reader = PdfViewer(item.data(Qt.UserRole), self, self.preview_page)
            self.reader.show()
        except PdfOpenCancelled:
            return
        except Exception as error:
            QMessageBox.warning(self, tr('PDF 열기 실패'), str(error))

    def change_page(self, delta):
        self.preview_page += delta
        self.render_preview()

    def render_preview(self):
        if self.busy():
            return
        self.preview.clear()
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.page_label.setText('— / —')
        item = self.files.currentItem()
        if item is None:
            self.preview.setText(tr('문서를 담으면\n이곳에 미리보기가 나타나요'))
            self.file_info.setText(tr('아직 선택한 파일이 없어요.'))
            return
        path = Path(item.data(Qt.UserRole))
        if path.suffix.lower() not in IMAGES | {'.pdf'}:
            self.preview.setText(tr('PDF로 변환한 뒤\n페이지를 미리 볼 수 있어요.'))
            self.file_info.setText(path.name)
            return
        try:
            with pdf.open(path) as doc:
                if doc.needs_pass:
                    raise ValueError(tr('암호를 해제한 사본을 추가해 주세요.'))
                self.preview_page = max(0, min(self.preview_page, doc.page_count - 1))
                page = doc[self.preview_page]
                scale = min(210 / page.rect.width, 246 / page.rect.height) * self.devicePixelRatioF()
                pix = page.get_pixmap(matrix=pdf.Matrix(scale, scale), alpha=False, colorspace=pdf.csRGB)
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
                thumbnail = QPixmap.fromImage(image)
                thumbnail.setDevicePixelRatio(self.devicePixelRatioF())
                self.preview.setPixmap(thumbnail)
                self.page_label.setText(f'{self.preview_page + 1} / {doc.page_count}')
                self.prev_button.setEnabled(self.preview_page > 0)
                self.next_button.setEnabled(self.preview_page < doc.page_count - 1)
                self.file_info.setText(tr('{v0}페이지 · {v1:.2f} MB', v0=doc.page_count, v1=path.stat().st_size / 1048576))
        except Exception:
            self.preview.setText(tr('미리보기를 열 수 없어요.\n암호 또는 파일 상태를 확인해 주세요.'))
            self.file_info.setText(path.name)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, tr('저장 폴더 선택'), self.folder.text())
        if path:
            self.folder.setText(path)

    def set_busy(self, busy):
        self.editor.setEnabled(not busy)
        for b in self.nav_buttons:
            b.setEnabled(not busy)
        self.folder.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)
        self.run_button.setEnabled(not busy and self.files.count() > 0)
        self.cancel_button.setVisible(busy)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)

    def start(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if self.busy() or not self.files.count():
            return
        if not self.folder.text().strip():
            self.status.setText(tr('결과를 저장할 폴더를 선택해 주세요.'))
            return
        if self.tool in {'merge', 'convert', 'summary'}:
            paths = tuple(self.files.item(i).data(Qt.UserRole) for i in range(self.files.count()))
        else:
            if not self.files.currentItem():
                self.status.setText(tr('목록에서 작업할 파일을 선택해 주세요.'))
                return
            paths = (self.files.currentItem().data(Qt.UserRole),)
        request = Request(self.tool, paths, self.folder.text().strip(), self.page_input.text(), (self.rotation.currentIndex() + 1) * 90)
        self.progress.setValue(0)
        self.open_button.hide()
        self.worker = Worker(request)
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(self.success)
        self.worker.failed.connect(self.failure)
        self.worker.batch_done.connect(self.batch_completed)
        self.worker.finished.connect(self.finished)
        self.set_busy(True)
        self.worker.start()

    def on_progress(self, value, message):
        self.progress.setValue(value)
        self.status.setText(message)

    def success(self, output):
        self.last_output = Path(output)
        size = self.last_output.stat().st_size / 1048576
        message = tr('저장 완료 · {v0:.2f} MB', v0=size)
        if self.tool == 'optimize':
            original = Path(self.worker.request.files[0]).stat().st_size
            ratio = 100 * (1 - self.last_output.stat().st_size / original)
            message += tr(' · {v0:.1f}% 감소', v0=ratio) if ratio > 0 else tr(' · 이미 최적화된 문서로 용량 감소가 없습니다.')
        self.status.setText(message)
        self.status.setToolTip(output)
        self.open_button.show()

    def failure(self, message):
        self.status.setText(message)
        self.progress.setValue(0)

    def batch_completed(self, result):
        outputs, errors = result['outputs'], result['errors']
        self.last_output = Path(outputs[0]) if outputs else None
        self.open_button.setVisible(bool(outputs))
        message = tr('완료 {v0}개 · 실패 {v1}개', v0=len(outputs), v1=len(errors))
        if result['cancelled']:
            message += tr(' · 취소됨 (이미 저장한 결과는 보존)')
        self.status.setText(message)
        self.status.setToolTip('\n'.join(outputs + errors))
        self.progress.setValue(100 if not errors and not result['cancelled'] else 0)
        if errors:
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr('작업 결과'))
            dialog.setText(message)
            dialog.setInformativeText(tr('실패한 파일은 저장되지 않았습니다. 상세 내용을 확인해 주세요.'))
            dialog.setDetailedText('\n'.join(errors))
            dialog.setModal(False)
            dialog.setAttribute(Qt.WA_DeleteOnClose)
            dialog.show()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)
        self.render_preview()

    def cancel(self):
        if self.worker:
            self.worker.requestInterruption()
            self.status.setText(tr('현재 단계가 끝나면 취소합니다…'))

    def open_result(self):
        if self.last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output.parent)))

    def closeEvent(self, event):
        dock = getattr(self, 'staging_dock', None)
        if self.busy() or (dock is not None and dock.worker is not None):
            self.status.setText(tr('작업을 취소하거나 완료한 뒤 창을 닫아 주세요.'))
            event.ignore()
        else:
            if dock is not None:
                dock.close()
            event.accept()

    def open_search(self):
        from .license_ui import ensure_license
        if ensure_license(self):
            from .search_ui import SearchDialog
            SearchDialog(self).exec()

    def help(self):
        QMessageBox.information(self, tr('어잉PDF 사용 안내'),
            tr('1. 왼쪽에서 도구를 선택하세요.\n2. 파일을 담고 미리보기를 확인하세요.\n'
            '3. 저장 위치를 고른 뒤 파란 버튼을 누르세요.\n\n'
            '합치기·변환·요약은 목록 전체를, 나머지는 선택한 파일 하나를 처리합니다.\n'
            '페이지 정리: 1-3, 5처럼 남길 페이지를 입력합니다. 3, 1, 2로 순서도 바꿀 수 있어요.\n'
            '원본은 수정하지 않으며, 같은 이름의 결과는 번호를 붙여 보관합니다.\n\n'
            'Office/한글 변환은 해당 앱 설치가 필요합니다. 스캔은 Windows OCR 언어팩을 사용합니다.\n'
            '문서 수정 시 전자서명 효력이나 일부 양식·책갈피가 유지되지 않을 수 있습니다.\n'
            '공식 제출 전에 결과 파일을 확인해 주세요.\n\n'
            'Pretendard · SIL OFL 1.1 / PySide6 · LGPLv3 / PyMuPDF · AGPLv3'))

    def menu_settings(self):
        from .package_context import is_packaged
        if is_packaged():
            from .shell import open_default_settings
            open_default_settings()
            self.status.setText(tr('Microsoft Store 설치판은 탐색기 메뉴가 패키지에 포함되어 있습니다.'))
            return
        from .shell import install, uninstall
        box = QMessageBox(self)
        box.setWindowTitle(tr('탐색기 우클릭 메뉴'))
        box.setText(tr('탐색기에서 바로 변환·합치기·요약을 실행할 수 있습니다.\nWindows 11에서는 “더 많은 옵션 표시”에 나타납니다.'))
        add = box.addButton(tr('등록'), QMessageBox.AcceptRole)
        default = box.addButton(tr('기본 PDF 앱 설정'), QMessageBox.ActionRole)
        remove = box.addButton(tr('해제'), QMessageBox.DestructiveRole)
        box.addButton(tr('닫기'), QMessageBox.RejectRole)
        box.exec()
        try:
            if box.clickedButton() == add:
                install()
                self.status.setText(tr('우클릭 메뉴를 등록했습니다.'))
            elif box.clickedButton() == remove:
                uninstall()
                self.status.setText(tr('우클릭 메뉴를 해제했습니다.'))
            elif box.clickedButton() == default:
                from .shell import open_default_settings
                install()
                open_default_settings()
        except Exception as error:
            QMessageBox.warning(self, tr('메뉴 설정 실패'), str(error))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='*')
    parser.add_argument('--screenshot')
    parser.add_argument('--dock', action='store_true', help='Open the floating file collection dock')
    parser.add_argument('--skip-update-once', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    from .localization import install_language
    install_language(app)
    app.setApplicationName('EoingPDF')
    app.setOrganizationName('Eoingtilab')
    app.setWindowIcon(QIcon(str(ROOT / 'assets/app_icon.png')))
    font_id = QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    if font_id < 0:
        raise RuntimeError(tr('Pretendard 폰트 파일을 찾을 수 없습니다.'))
    ui_font = QFont('Pretendard', 10)
    ui_font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(ui_font)
    app.setStyle('Fusion')
    from .sdk_theme import install_theme
    install_theme(app)
    from .sdk_theme import apply_style
    apply_style(app, STYLE)
    log_folder = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / 'logs'
    from logging.handlers import RotatingFileHandler
    try:
        log_folder.mkdir(parents=True, exist_ok=True)
        log_handler = RotatingFileHandler(log_folder / 'app.log', maxBytes=1048576, backupCount=2, encoding='utf-8')
    except OSError:
        import tempfile
        log_folder = Path(tempfile.gettempdir()) / 'EoingPDF-logs'
        try:
            log_folder.mkdir(parents=True, exist_ok=True)
            log_handler = RotatingFileHandler(log_folder / 'app.log', maxBytes=1048576, backupCount=2, encoding='utf-8')
        except OSError:
            log_handler = logging.NullHandler()
    logging.basicConfig(handlers=[log_handler], level=logging.INFO)
    from .license_ui import ensure_license
    if not ensure_license():
        return
    if args.dock:
        from .staging_dock import StagingDock
        window = StagingDock()
        window.add_files(args.files)
    elif len(args.files) == 1 and Path(args.files[0]).suffix.lower() == '.pdf':
        from .viewer import PdfViewer, PdfOpenCancelled
        try:
            window = PdfViewer(args.files[0])
        except PdfOpenCancelled:
            return
        except Exception as error:
            QMessageBox.warning(None, tr('PDF 열기 실패'), str(error))
            return
    else:
        window = Window()
    window.show()
    from .updates import start_updates
    start_updates(app, window)
    if args.files and isinstance(window, Window):
        window.add_files(args.files)
    if args.screenshot:
        def capture():
            window.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(600, capture)
    sys.exit(app.exec())
