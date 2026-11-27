"""Task-oriented PDF workbench: reader, multi-tool, library, inline tools, and presentations."""
from .localization import tr
from .sdk_theme import apply_style
from pathlib import Path
import pymupdf as pdf
from PySide6.QtCore import Qt, QEvent, QTimer, QSize, QPoint, Signal, QRectF
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence, QIcon, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox, QComboBox,
    QInputDialog, QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QListView,
    QWidget, QAbstractSpinBox, QAbstractItemView, QLineEdit, QStyle, QStackedWidget,
    QTabWidget, QFrame,
)
from .core import open_pdf, pages_from_text, Request, run
from .page_edits import apply_page_order
from .action_icons import action_icon, set_action_icon, tool_icon

THUMBNAIL_CARD_LIMIT = 24


def delete_pages(path, selection, folder):
    with open_pdf(path) as document:
        removed = set(pages_from_text(selection, document.page_count))
        kept = [str(index + 1) for index in range(document.page_count) if index not in removed]
    if not kept:
        raise ValueError(tr('모든 페이지를 삭제할 수 없습니다. 한 페이지 이상 남겨 주세요.'))
    return run(Request('extract', (str(path),), str(folder), ','.join(kept)))


class PdfOpenCancelled(ValueError):
    """User cancelled password entry; leave any existing document intact."""


class _FlexibleStack(QStackedWidget):
    """Stacked container that follows the active page size hint so hidden boards do not widen narrow layouts."""

    def sizeHint(self):
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self):
        current = self.currentWidget()
        if current is None:
            return QSize(120, 120)
        hint = current.minimumSizeHint()
        return QSize(min(hint.width(), 140), min(hint.height(), 120))


def unlock_viewer_pdf(path, parent=None, password=''):
    """Authenticate in memory; never create a decrypted temporary document."""
    with pdf.open(path) as document:
        if not document.is_pdf or not document.page_count:
            raise ValueError(tr('페이지가 있는 PDF 파일을 선택해 주세요.'))
        while document.needs_pass and not document.authenticate(password):
            password, accepted = QInputDialog.getText(
                parent, tr('PDF 암호 입력'),
                tr('문서를 열기 위한 암호를 입력해 주세요. 암호는 저장하지 않습니다.'),
                QLineEdit.Password)
            if not accepted:
                raise PdfOpenCancelled(tr('PDF 열기를 취소했습니다.'))
            if not document.authenticate(password):
                QMessageBox.warning(parent, tr('암호 확인'), tr('암호가 맞지 않습니다. 다시 입력해 주세요.'))
        return password, document.page_count


class PageSidebar(QListWidget):
    order_changed = Signal(object)

    def dropEvent(self, event):
        current = self.currentItem().data(Qt.UserRole) if self.currentItem() else None
        before = [self.item(i).data(Qt.UserRole) for i in range(self.count())]
        super().dropEvent(event)
        after = [self.item(i).data(Qt.UserRole) for i in range(self.count())]
        if after != before:
            QTimer.singleShot(0, lambda payload=(after, current): self.order_changed.emit(payload))


class PdfViewer(QDialog):
    def __init__(self, path=None, parent=None, page=0, paths=None):
        super().__init__(parent)
        initial_paths = [Path(p) for p in (paths or []) if p]
        if path is not None:
            initial_paths.insert(0, Path(path))
        first_pdf = next((p for p in initial_paths if p.suffix.lower() == '.pdf' and p.is_file()), None)
        if path is not None:
            first_pdf = Path(path)

        self.path = first_pdf
        if self.path is not None:
            self.password, self.count = unlock_viewer_pdf(self.path, self)
            self.pages = list(range(self.count))
            self.source_count = self.count
            self.original_path = self.path
            self.setWindowTitle(tr('{v0} · 어잉PDF', v0=self.path.name))
        else:
            self.password, self.count = '', 0
            self.pages = []
            self.source_count = 0
            self.original_path = Path.home() / 'document.pdf'
            self.setWindowTitle(tr('어잉PDF · EoingPDF'))

        self.stamp_editor = None
        self.visible_page_size = (1, 1)
        self.preview_owners = []
        self.edit_history = None
        self._history_restoring = False
        self.materialized_path = None
        self._materialized_state = None
        self.thumbnail_mode = True
        self.thumbnail_cache = set()
        self.dirty = False
        self.search_hit = None
        self.slideshow = None
        self._last_fit_render = None
        self.quick_worker = None
        self.setAcceptDrops(True)
        self.resize(1140, 820)
        self.setMinimumSize(680, 480)
        apply_style(self, 'QDialog {background:#f7f9fc;} QScrollArea {background:#e8edf5;border:0;} QListWidget {background:#eef2f8;border:0;color:#263246;} QListWidget::item:selected {background:#dbe6ff;border:2px solid #5176ec;border-radius:6px;} QSpinBox, QComboBox {background:white;color:#263246;border:1px solid #dae2f0;border-radius:6px;padding:6px;min-width:70px;}')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        from .capture_ui import CaptureChip
        self.capture_chip = CaptureChip(self)
        layout.addWidget(self.capture_chip)

        toolbar_card = QFrame()
        toolbar_card.setObjectName('viewerToolbar')
        apply_style(toolbar_card, 'QFrame#viewerToolbar {background:#ffffff; border:1px solid #e2e7ef; border-radius:8px; padding:2px 6px;}')
        navigation = QHBoxLayout(toolbar_card)
        navigation.setContentsMargins(4, 2, 4, 2)
        navigation.setSpacing(3)
        self.previous = QPushButton()
        set_action_icon(self.previous, 'previous')
        self.previous.setToolTip(tr('이전 페이지'))
        self.previous.setAccessibleName(tr('이전 페이지'))
        self.next = QPushButton()
        set_action_icon(self.next, 'next')
        self.next.setToolTip(tr('다음 페이지'))
        self.next.setAccessibleName(tr('다음 페이지'))
        for navigation_button in (self.previous, self.next):
            navigation_button.setFixedSize(30, 32)
            apply_style(navigation_button, 'QPushButton {padding:0;}')

        self.page = QSpinBox()
        self.page.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.page.setRange(1, max(1, self.count))
        self.page.setValue(max(1, min(page + 1, max(1, self.count))))
        self.page.setSuffix(f' / {self.count}')

        self.zoom = QComboBox()
        apply_style(self.zoom, 'QComboBox {background:#ffffff;color:#263246;} QComboBox QAbstractItemView {background:#ffffff;color:#263246;selection-background-color:#dbe6ff;selection-color:#183b8f;border:1px solid #dae2f0;outline:0;} QComboBox QAbstractItemView::item {min-height:28px;padding:4px 8px;}')
        self.zoom.addItems([tr('너비 맞춤'), tr('페이지 맞춤'), '50%', '75%', '100%', '125%', '150%', '200%'])

        navigation.addWidget(self.previous)
        navigation.addWidget(self.next)
        navigation.addWidget(QLabel(tr('페이지')))
        navigation.addWidget(self.page)

        step_controls = QHBoxLayout()
        step_controls.setSpacing(0)
        for text, delta in [('▲', -1), ('▼', 1)]:
            step = QPushButton(text)
            step.setAutoDefault(False)
            step.setFixedSize(34, 28)
            apply_style(step, 'QPushButton {padding:0;color:#263246;background:white;border:1px solid #dae2f0;border-radius:3px;font-size:12px;}')
            step.setToolTip(tr('다음 페이지') if delta > 0 else tr('이전 페이지'))
            step.setAccessibleName(tr('다음 페이지') if delta > 0 else tr('이전 페이지'))
            step.clicked.connect(lambda checked=False, d=delta: self.page.stepBy(d))
            step_controls.addWidget(step)
        navigation.addLayout(step_controls)

        self.zoom_out_button = QPushButton()
        set_action_icon(self.zoom_out_button, 'zoom_out')
        self.zoom_out_button.setFixedSize(30, 32)
        apply_style(self.zoom_out_button, 'QPushButton {padding:0;}')
        self.zoom_out_button.setToolTip(tr('축소 · Ctrl+마우스 휠'))
        self.zoom_out_button.clicked.connect(lambda: self.adjust_zoom(-1))
        navigation.addWidget(self.zoom_out_button)
        navigation.addWidget(self.zoom)

        self.zoom_in_button = QPushButton()
        set_action_icon(self.zoom_in_button, 'zoom_in')
        self.zoom_in_button.setFixedSize(30, 32)
        apply_style(self.zoom_in_button, 'QPushButton {padding:0;}')
        self.zoom_in_button.setToolTip(tr('확대 · Ctrl+마우스 휠'))
        self.zoom_in_button.clicked.connect(lambda: self.adjust_zoom(1))
        navigation.addWidget(self.zoom_in_button)

        def nav_icon_btn(icon_name, tooltip, callback):
            b = QPushButton()
            b.setAutoDefault(False)
            b.setFixedSize(30, 32)
            set_action_icon(b, icon_name)
            apply_style(b, 'QPushButton {padding:0;}')
            b.setToolTip(tr(tooltip))
            b.setAccessibleName(tr(tooltip))
            b.clicked.connect(callback)
            navigation.addWidget(b)
            return b

        self.rotate_left_button = nav_icon_btn('undo', '현재 문서 반시계 90° 회전', lambda: self.quick_rotate(270))
        self.rotate_right_button = nav_icon_btn('redo', '현재 문서 시계 90° 회전', lambda: self.quick_rotate(90))
        self.sign_draw_button = nav_icon_btn('pen', '서명 직접 그리기 · 도장 만들기', self.open_sign_draw)
        self.multitool_nav_button = nav_icon_btn('pages', '페이지 멀티툴 편집기', lambda: self.toggle_multi_tool())
        self.info_button = nav_icon_btn('history', 'PDF 상세 정보 · 규격 검사', self.open_pdf_info)

        self.print_button = QPushButton()
        set_action_icon(self.print_button, 'print')
        self.print_button.setFixedSize(34, 32)
        self.print_button.setToolTip(tr('인쇄 준비'))
        self.print_button.setAccessibleName(tr('인쇄 준비'))
        apply_style(self.print_button, 'QPushButton {padding:0;}')
        from .viewer_workspace import action_menu
        print_menu = action_menu(self.print_button)
        for title, action in [(tr('밝은 인쇄용 사본'), 'print_light'), (tr('4쪽 모아찍기'), 'four_up'), (tr('소책자 인쇄 배치'), 'booklet')]:
            item = print_menu.addAction(tool_icon(action, 'view', print_menu), tr(title))
            item.triggered.connect(lambda checked=False, key=action: self.diagnostic_action(key))
        print_menu.aboutToShow.connect(lambda: self.sniffer.start(self.path, trigger='print') if self.path else None)
        self.print_button.setMenu(print_menu)
        navigation.addWidget(self.print_button)
        navigation.addStretch(1)

        from .sniffer_ui import MicroSniffer
        self.sniffer = MicroSniffer(self)
        self.sniffed_path = None
        self.suggested_name = ''
        self.sniffer.result.connect(self.handle_diagnostics)

        from .page_scroll import PageScrollArea
        self.scroll = PageScrollArea()
        self.scroll.page_requested.connect(self.scroll_page)
        self._wheel_bottom_page = None
        self.scroll.interacted.connect(self.clear_scroll_landing)
        self.scroll.verticalScrollBar().sliderMoved.connect(self.clear_scroll_landing)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._keep_previous_page_bottom)
        self.scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        from .selection_canvas import SelectionCanvas
        self.canvas = SelectionCanvas()
        self.canvas.selected.connect(self.copy_selected_table)
        self.canvas.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.canvas)

        from .library_panel import LibraryPanel
        self.library_panel = LibraryPanel(self)
        self.library_panel.open_requested.connect(self._switch_from_library)
        self.library_panel.batch_merge_requested.connect(self.run_library_merge)
        self.library_panel.batch_convert_requested.connect(self.run_library_convert)

        self.thumbnails = PageSidebar()
        self.thumbnails.setFixedWidth(156)
        self.thumbnails.setViewMode(QListView.IconMode)
        self.thumbnails.setMovement(QListView.Snap)
        self.thumbnails.setDragDropMode(QAbstractItemView.InternalMove)
        self.thumbnails.setDefaultDropAction(Qt.MoveAction)
        self.thumbnails.setDragEnabled(True)
        self.thumbnails.setAcceptDrops(True)
        self.thumbnails.setDropIndicatorShown(True)
        self.thumbnails.setWrapping(False)
        self.thumbnails.setFlow(QListView.TopToBottom)
        self.thumbnails.setIconSize(QSize(112, 144))
        self.thumbnails.setSpacing(5)
        self.thumbnails.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumbnails.order_changed.connect(self.apply_sidebar_order)
        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setSingleShot(True)
        self.thumbnail_timer.timeout.connect(self.fill_thumbnails)
        self.thumbnails.verticalScrollBar().valueChanged.connect(lambda: self.thumbnail_timer.start(30))
        self.thumbnails.currentRowChanged.connect(lambda row: self.page.setValue(row + 1) if row >= 0 else None)

        from .viewer_workspace import WorkspaceHeader
        self.workspace_header = WorkspaceHeader(self)
        layout.addWidget(self.workspace_header)
        self.update_banner_host = QVBoxLayout()
        self.update_banner_host.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.update_banner_host)
        layout.addWidget(toolbar_card)

        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.render)
        self.scroll.viewport().installEventFilter(self)
        self.canvas.installEventFilter(self)

        body = QHBoxLayout()
        body.setSpacing(0)
        from .viewer_workspace import NavigationStrip
        self.navigation_strip = NavigationStrip(self)
        body.addWidget(self.navigation_strip)

        self.thumbnail_container = QWidget(self)
        self.thumbnail_container.setObjectName('thumbnailPanel')
        self.thumbnail_container.setFixedWidth(224)
        self.thumbnails.setFixedWidth(212)
        left_wrap = QVBoxLayout(self.thumbnail_container)
        left_wrap.setContentsMargins(0, 0, 0, 0)
        left_wrap.setSpacing(0)

        self.left_tabs = QTabWidget(self.thumbnail_container)
        self.left_tabs.setDocumentMode(True)

        pages_tab = QWidget()
        thumb_layout = QVBoxLayout(pages_tab)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(0)
        thumb_header = QHBoxLayout()
        thumb_header.setContentsMargins(8, 2, 3, 2)
        thumb_header.addWidget(QLabel(tr('페이지 목록')), 1)
        self.close_thumbnails_button = QPushButton()
        set_action_icon(self.close_thumbnails_button, 'close')
        self.close_thumbnails_button.setFixedSize(28, 28)
        apply_style(self.close_thumbnails_button, 'QPushButton {padding:0;}')
        self.close_thumbnails_button.setToolTip(tr('페이지 목록 닫기'))
        self.close_thumbnails_button.setAccessibleName(tr('페이지 목록 닫기'))
        self.close_thumbnails_button.clicked.connect(lambda: self.sidebar_toggle.setChecked(False))
        thumb_header.addWidget(self.close_thumbnails_button)
        thumb_layout.addLayout(thumb_header)
        thumb_layout.addWidget(self.thumbnails, 1)

        self.left_tabs.addTab(pages_tab, tr('페이지'))
        self.left_tabs.addTab(self.library_panel, tr('보관함'))
        left_wrap.addWidget(self.left_tabs, 1)

        apply_style(
            self.thumbnail_container,
            'QWidget#thumbnailPanel {background:#ffffff; border-right:1px solid #e2e7ef;}'
            'QTabBar::tab {background:#eef2f8; color:#657187; border-radius:6px; padding:5px 10px; margin:4px 2px; font-weight:600; font-size:12px;}'
            'QTabBar::tab:selected {background:#edf2ff; color:#183b8f; border:1px solid #c6d3e6;}',
        )
        self.thumbnail_container.hide()
        body.addWidget(self.thumbnail_container)
        self.sidebar_toggle.setChecked(True)

        from .multi_tool_ui import MultiToolWidget
        self.multi_tool = MultiToolWidget(self)
        self.multi_tool.close_requested.connect(lambda: self.toggle_multi_tool(False))

        self.empty_home = self._build_empty_home()

        self.center_stack = _FlexibleStack(self)
        self.center_stack.addWidget(self.scroll)
        self.center_stack.addWidget(self.multi_tool)
        self.center_stack.addWidget(self.empty_home)
        self.center_stack.currentChanged.connect(lambda _idx: self.center_stack.updateGeometry())
        body.addWidget(self.center_stack, 1)
        body.addWidget(self.workspace_header.editing_panel)
        layout.addLayout(body, 1)

        self.status = QLabel(tr('원본은 수정하지 않습니다'))
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.restore_status)
        footer = QHBoxLayout()
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        from .product_policy import LICENSE_REQUIRED
        from .updates import show_update_status
        self.shortcuts_button = QPushButton(tr('단축키 · F1'))
        set_action_icon(self.shortcuts_button, 'list')
        self.shortcuts_button.setAutoDefault(False)
        self.shortcuts_button.clicked.connect(self.open_shortcuts_dialog)
        footer.addWidget(self.shortcuts_button)
        self.settings_button = QPushButton(tr('설정·도움말'))
        set_action_icon(self.settings_button, 'settings')
        self.settings_button.setAutoDefault(False)
        settings_menu = action_menu(self.settings_button)
        settings_menu.addAction(action_icon('settings', settings_menu), tr('설정')).triggered.connect(self.open_settings_dialog)
        if LICENSE_REQUIRED:
            from .license_ui import settings
            settings_menu.addAction(action_icon('license', settings_menu), tr('라이선스')).triggered.connect(lambda: settings(self))
        settings_menu.addAction(action_icon('update', settings_menu), tr('업데이트')).triggered.connect(lambda: show_update_status(self))
        settings_menu.addAction(action_icon('list', settings_menu), tr('단축키 안내 · F1')).triggered.connect(self.open_shortcuts_dialog)
        self.settings_button.setMenu(settings_menu)
        footer.addWidget(self.settings_button)
        layout.addLayout(footer)

        self.previous.clicked.connect(lambda: self.page.setValue(self.page.value() - 1))
        self.next.clicked.connect(lambda: self.page.setValue(self.page.value() + 1))
        self.page.valueChanged.connect(self.render)
        self.zoom.currentIndexChanged.connect(self.render)
        for key, delta in [('PgDown', 1), ('PgUp', -1)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda d=delta: self.page.setValue(self.page.value() + d))

        if initial_paths:
            self.library_panel.add_paths(initial_paths)
        self.update_more_features()
        if self.path is not None:
            self.library_panel.highlight_active(self.path)
            self.center_stack.setCurrentIndex(0)
            self.reset_thumbnails()
            self.render()
            self.reset_edit_history()
        else:
            self.left_tabs.setCurrentIndex(1)
            self.center_stack.setCurrentIndex(2)
            self.previous.setEnabled(False)
            self.next.setEnabled(False)
            self.save_as_button.setEnabled(False)

        def bind_key(seq, handler):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(handler)
            return sc

        def jump_edge(end_page: bool):
            from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit
            focus = QApplication.focusWidget()
            if isinstance(focus, (QLineEdit, QAbstractSpinBox, QPlainTextEdit, QTextEdit)):
                return
            if self.count > 0:
                self.page.setValue(self.count if end_page else 1)

        bind_key('F1', self.open_shortcuts_dialog)
        bind_key('F5', self.start_slideshow)
        bind_key('Shift+F5', self.start_slideshow)
        bind_key('Ctrl+S', self.save_changes)
        bind_key('Ctrl+O', self.choose_pdf)
        bind_key('Ctrl+W', self.close)
        bind_key('Ctrl+P', lambda: self.print_button.showMenu())
        bind_key('Ctrl+I', self.open_pdf_info)
        bind_key('Ctrl+M', lambda: self.toggle_multi_tool())
        bind_key('Ctrl+D', self.open_sign_draw)
        bind_key('Ctrl+F', lambda: self.diagnostic_action('search_docs'))
        bind_key('Ctrl+B', lambda: self.sidebar_toggle.toggle())
        bind_key('Ctrl+J', lambda: self.editing_toggle.toggle())
        bind_key('Ctrl++', lambda: self.adjust_zoom(1))
        bind_key('Ctrl+=', lambda: self.adjust_zoom(1))
        bind_key('Ctrl+-', lambda: self.adjust_zoom(-1))
        bind_key('Ctrl+0', lambda: self.zoom.setCurrentIndex(4))
        bind_key('Ctrl+1', lambda: self.zoom.setCurrentIndex(0))
        bind_key('Ctrl+2', lambda: self.zoom.setCurrentIndex(1))
        bind_key('Ctrl+R', lambda: self.quick_rotate(90))
        bind_key('Ctrl+Shift+R', lambda: self.quick_rotate(270))
        bind_key('Home', lambda: jump_edge(False))
        bind_key('End', lambda: jump_edge(True))

    def _build_empty_home(self) -> QWidget:
        from PySide6.QtWidgets import QGridLayout
        panel = QWidget(self)
        panel.setObjectName('emptyHome')
        outer = QVBoxLayout(panel)
        outer.setAlignment(Qt.AlignCenter)
        outer.setSpacing(14)

        box = QFrame()
        box.setObjectName('dropHomeCard')
        box.setMaximumWidth(620)
        card = QVBoxLayout(box)
        card.setContentsMargins(32, 28, 32, 28)
        card.setSpacing(12)

        badge = QLabel(tr('● 내 PC에서 100% 안전하게 · 오프라인 PDF 작업실'))
        badge.setObjectName('homeBadge')
        badge.setAlignment(Qt.AlignCenter)
        card.addWidget(badge, 0, Qt.AlignHCenter)

        title = QLabel(tr('Your PDFs. Your control. · 어잉PDF'))
        title.setStyleSheet('font-size:22px;font-weight:700;')
        title.setAlignment(Qt.AlignCenter)
        card.addWidget(title)

        sub = QLabel(tr('여기에 PDF, 이미지, Office, 한글 파일을 끌어다 놓거나\n아래 버튼으로 문서를 열어 65+ 도구를 바로 시작하세요.'))
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignCenter)
        card.addWidget(sub)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        open_btn = QPushButton(tr('PDF 열기 (Ctrl+O)'))
        open_btn.setObjectName('primary')
        set_action_icon(open_btn, 'open')
        open_btn.clicked.connect(self.choose_pdf)
        btn_row.addWidget(open_btn)

        add_btn = QPushButton(tr('보관함에 파일 담기'))
        set_action_icon(add_btn, 'pages')
        add_btn.clicked.connect(self.library_panel.choose_files)
        btn_row.addWidget(add_btn)
        card.addLayout(btn_row)

        quick_grid = QGridLayout()
        quick_grid.setSpacing(6)
        for idx, (label, cb, icon_name) in enumerate((
            ('문서 합치기', lambda: self.diagnostic_action('merge'), 'pages'),
            ('PDF 변환', lambda: self.diagnostic_action('convert_to_pdf'), 'export'),
            ('슬라이드쇼 · F5', self.start_slideshow, 'play'),
            ('직인·서명 넣기', self.insert_stamp, 'stamp'),
            ('페이지 멀티툴', lambda: self.toggle_multi_tool(True), 'thumbnail'),
            ('파이프라인', lambda: self.diagnostic_action('pipeline'), 'tools'),
        )):
            qb = QPushButton(tr(label))
            qb.setAutoDefault(False)
            qb.setMinimumWidth(0)
            set_action_icon(qb, icon_name)
            qb.clicked.connect(cb)
            quick_grid.addWidget(qb, idx // 3, idx % 3)
        card.addLayout(quick_grid)

        outer.addWidget(box)
        apply_style(
            panel,
            'QWidget#emptyHome {background:#e8edf5;}'
            'QFrame#dropHomeCard {background:#ffffff;border:1px solid #e2e7ef;border-radius:16px;}'
            'QLabel#homeBadge {background:#ecf6f2;color:#458475;border:1px solid #c6d3e6;border-radius:12px;padding:4px 12px;font-size:11px;font-weight:600;}'
            'QPushButton {background:#f7f9fc;border:1px solid #dae2f0;border-radius:8px;padding:8px 12px;font-size:12px;}'
            'QPushButton:hover {background:#edf2ff;border-color:#7c9dfa;}'
            'QPushButton#primary {background:#416ae6;color:white;border:0;border-radius:8px;padding:10px 16px;font-weight:600;font-size:13px;}'
            'QPushButton#primary:hover {background:#3e61d8;}',
        )
        return panel

    def show_empty_home(self):
        self.center_stack.setCurrentIndex(2)
        self.multitool_rail_button.setChecked(False)

    def add_to_library(self, paths):
        added = self.library_panel.add_paths(paths)
        if self.path is None:
            first_pdf = next((p for p in added if p.suffix.lower() == '.pdf'), None)
            if first_pdf is not None:
                try:
                    self.load(first_pdf)
                except Exception as error:
                    QMessageBox.warning(self, tr('PDF 열기 실패'), str(error))

    def _switch_from_library(self, path_str: str):
        from .library_panel import _safe_resolve
        target = _safe_resolve(path_str)
        if self.path is not None and target == _safe_resolve(self.path):
            self.center_stack.setCurrentIndex(0)
            self.multitool_rail_button.setChecked(False)
            return
        if not self.confirm_leave():
            return
        try:
            self.load(target)
        except PdfOpenCancelled:
            return
        except Exception as error:
            QMessageBox.warning(self, tr('PDF 열기 실패'), str(error))

    def open_library_tab(self):
        self.sidebar_toggle.setChecked(True)
        self.left_tabs.setCurrentIndex(1)

    def open_history_dialog(self):
        if self.edit_history is None:
            return
        from .viewer_workspace import HistoryDialog
        HistoryDialog(self).exec()

    def open_staging_dock(self):
        from .staging_dock import show_dock
        show_dock(self)

    def open_pdf_info(self):
        if self.path is None:
            QMessageBox.information(self, tr('PDF 상세 정보'), tr('먼저 PDF 파일을 열어 주세요.'))
            return
        from .workbench_dialogs import PdfInfoDialog
        PdfInfoDialog(self.path, self.password, self).exec()

    def open_settings_dialog(self):
        from .settings_ui import SettingsDialog
        SettingsDialog(self).exec()

    def open_shortcuts_dialog(self):
        from .workbench_dialogs import ShortcutsDialog
        ShortcutsDialog(self).exec()

    def open_sign_draw(self):
        if self.path is None:
            QMessageBox.information(self, tr('서명 그리기'), tr('먼저 PDF 파일을 열어 주세요.'))
            return
        from .workbench_dialogs import SignDrawDialog
        dialog = SignDrawDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.result_png_path is not None:
            if self.stamp_editor is None:
                from .stamp_editor import StampEditor
                self.stamp_editor = StampEditor(self)
            try:
                self.stamp_editor.add_image(dialog.result_png_path)
            except Exception as error:
                QMessageBox.warning(self, tr('직인 이미지 열기 실패'), str(error))

    def save_as(self):
        if self.path is None:
            QMessageBox.information(self, tr('다른 이름으로 저장'), tr('먼저 PDF 파일을 열어 주세요.'))
            return
        from .workbench_dialogs import SaveAsDialog
        SaveAsDialog(self).exec()

    def toggle_multi_tool(self, enable=None):
        if self.path is None:
            QMessageBox.information(self, tr('페이지 멀티툴'), tr('먼저 PDF 파일을 열어 주세요.'))
            self.multitool_rail_button.setChecked(False)
            return
        if enable is None:
            enable = self.center_stack.currentIndex() != 1
        if enable:
            self.multi_tool.load_from_viewer()
            self.center_stack.setCurrentIndex(1)
            self.multitool_rail_button.setChecked(True)
        else:
            self.center_stack.setCurrentIndex(0)
            self.multitool_rail_button.setChecked(False)

    def quick_rotate(self, delta: int):
        if self.path is None:
            return
        import tempfile
        owner = tempfile.TemporaryDirectory(prefix='eoing-rot-')
        target = Path(owner.name) / 'rotated.pdf'
        try:
            source = self.stage_current_preview(display=False)
            with open_pdf(source, self.password) as doc:
                for p in doc:
                    p.set_rotation((p.rotation + delta) % 360)
                doc.save(target, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_KEEP)
            self.apply_preview(str(target), self.password, owner, label='페이지 회전')
        except Exception as error:
            owner.cleanup()
            QMessageBox.warning(self, tr('회전 실패'), str(error))

    def run_library_merge(self, raw_paths: list[str] | None = None):
        paths = raw_paths or self.library_panel.checked_or_all()
        if not paths:
            from .convert import SUPPORTED
            ext_filter = tr('지원 문서') + ' (' + ' '.join('*' + ext for ext in sorted(SUPPORTED)) + ')'
            paths, _ = QFileDialog.getOpenFileNames(self, tr('합칠 파일 선택'), '', ext_filter)
            if not paths:
                return
            self.library_panel.add_paths(paths)
        folder = QFileDialog.getExistingDirectory(self, tr('합친 PDF 저장 폴더 선택'), str(Path(paths[0]).parent))
        if not folder:
            return
        self._start_quick_batch('merge', paths, folder)

    def run_library_convert(self, raw_paths: list[str] | None = None):
        paths = raw_paths or self.library_panel.checked_or_all()
        if not paths:
            from .convert import SUPPORTED
            ext_filter = tr('지원 문서') + ' (' + ' '.join('*' + ext for ext in sorted(SUPPORTED)) + ')'
            paths, _ = QFileDialog.getOpenFileNames(self, tr('PDF로 변환할 파일 선택'), '', ext_filter)
            if not paths:
                return
            self.library_panel.add_paths(paths)
        folder = QFileDialog.getExistingDirectory(self, tr('변환 결과 저장 폴더 선택'), str(Path(paths[0]).parent))
        if not folder:
            return
        self._start_quick_batch('convert', paths, folder)

    def _start_quick_batch(self, action: str, paths: list[str], folder: str):
        if self.quick_worker and self.quick_worker.isRunning():
            return
        from .quick import QuickWorker
        self.quick_worker = QuickWorker(action, paths, folder)
        self.quick_worker.progress.connect(lambda _v, msg: self.status.setText(msg))
        self.quick_worker.result.connect(self._on_quick_batch_done)
        self.status.setText(tr('작업을 시작했습니다…'))
        self.quick_worker.start()

    def _on_quick_batch_done(self, result: dict):
        outputs = result.get('outputs', [])
        errors = result.get('errors', [])
        self.show_feedback(tr('완료 {done}개 · 실패 {failed}개', done=len(outputs), failed=len(errors)))
        if outputs:
            self.library_panel.add_paths(outputs)
            first_pdf = next((p for p in outputs if str(p).lower().endswith('.pdf')), None)
            if first_pdf:
                try:
                    if not self.dirty:
                        self.load(first_pdf)
                except Exception:
                    pass
        if errors:
            QMessageBox.warning(self, tr('작업 일부 실패'), '\n'.join(errors[:10]))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.add_to_library(paths)
            first_pdf = next((Path(p) for p in paths if Path(p).suffix.lower() == '.pdf'), None)
            if first_pdf is not None and not self.dirty:
                try:
                    self.load(first_pdf)
                except Exception:
                    pass
        event.acceptProposedAction()

    def open_advanced_dialog(self, action='target_size'):
        if self.path is None:
            QMessageBox.information(self, tr('도구 실행'), tr('먼저 PDF 파일을 열어 주세요.'))
            return
        try:
            source = self.stage_current_preview(display=False)
        except Exception as error:
            QMessageBox.warning(self, tr('미리보기 실패'), str(error))
            return
        from .advanced_ui import AdvancedDialog
        dialog = AdvancedDialog(self)
        dialog.source.setText(str(source))
        dialog.password.setText(self.password)
        idx = dialog.tool.findData(action)
        if idx >= 0:
            dialog.tool.setCurrentIndex(idx)
        dialog.exec()

    def start_slideshow(self):
        if self.path is None:
            QMessageBox.information(self, tr('슬라이드쇼'), tr('먼저 PDF 파일을 열어 주세요.'))
            return
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if self.slideshow is not None and self.slideshow.isVisible():
            self.slideshow.raise_()
            self.slideshow.activateWindow()
            return
        if self.stamp_editor and self.stamp_editor.stamps:
            try:
                source = self.stage_current_preview(display=False)
            except Exception as error:
                QMessageBox.warning(self, tr('미리보기 실패'), str(error))
                return
            pages = list(range(self.count))
        else:
            source = self.path
            pages = self.pages
        self.slideshow = SlideShow(source, self.page.value() - 1, self, pages, password=self.password)
        self.slideshow.viewer_draft_path = source
        self.slideshow.setWindowModality(Qt.WindowModal)
        slides = self.slideshow
        slides.finished.connect(lambda _: self.finish_slideshow(slides))
        screens = QGuiApplication.screens()
        main_screen = self.screen()
        secondary = next((screen for screen in screens if screen != main_screen), None)
        if secondary is not None:
            slides.winId()
            slides.windowHandle().setScreen(secondary)
            slides.setGeometry(secondary.geometry())
            slides.setWindowModality(Qt.NonModal)
            slides.exit_button.hide()
            slides.presenter_button.hide()
            slides.hint.hide()
        self.slideshow.showFullScreen()
        self.slideshow.activateWindow()
        self.slideshow.setFocus()
        if secondary is not None:
            slides.show_presenter(main_screen)

    def copy_page_image(self):
        if self.path is None:
            return
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        try:
            from .clipboard_tools import copy_page
            source = self.stage_current_preview(display=False)
            with open_pdf(source, self.password) as doc:
                copy_page(doc[self.page.value() - 1], int(self.winId()))
            self.show_feedback(tr('300DPI 페이지 이미지를 복사했습니다.'))
        except Exception as error:
            self.show_feedback(tr('이미지 복사 실패: {error}', error=tr(str(error))))

    def copy_selected_table(self, rect):
        if self.path is None:
            return
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        try:
            from .clipboard_tools import selection_rect, extract_table, copy_table
            with open_pdf(self.path, self.password) as doc:
                page = doc[self.pages[self.page.value() - 1]]
                clip = selection_rect(page, (rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height()),
                                      (self.canvas.width(), self.canvas.height()))
                rows = extract_table(page, clip)
                copy_table(rows, int(self.winId()))
            self.show_feedback(tr('{count}행 표를 복사했습니다. Excel에 붙여넣을 수 있습니다.', count=len(rows)))
        except Exception as error:
            self.show_feedback(tr('표 복사 실패: {error}', error=tr(str(error))))

    def show_feedback(self, message):
        self.status.setText(message)
        self.feedback_timer.start(5000)

    def restore_status(self):
        self.status.setText(tr('저장하지 않은 변경이 있어요 · 저장 버튼으로 새 PDF를 만드세요') if self.dirty else tr('원본은 수정하지 않습니다'))

    def handle_diagnostics(self, report):
        name = report.get('suggested_name', '') if isinstance(report, dict) else ''
        self.suggested_name = name if isinstance(name, str) else ''
        self.update_more_features()

    def update_more_features(self):
        self.more_features_menu.clear()
        self.recommended_name_action.setVisible(bool(self.suggested_name))
        from .tool_catalog import CATEGORIES, find_tools
        for group in CATEGORIES:
            menu = self.more_features_menu.addMenu(tr(group.title))
            menu.menuAction().setIcon(tool_icon('', group.key, menu))
            for entry in find_tools(category=group.key):
                action = menu.addAction(tool_icon(entry.key, entry.category, menu), tr(entry.title))
                action.triggered.connect(lambda checked=False, tool=entry.key: self.diagnostic_action(tool))
        if self.suggested_name:
            self.more_features_menu.addSeparator()
            suggested_name_action = self.more_features_menu.addAction(action_icon('rename', self.more_features_menu), tr('제목으로 파일명 추천'))
            suggested_name_action.triggered.connect(lambda: self.diagnostic_action('rename'))
        self.update_sidebar_mode_action()

    def show_all_tools(self, category='all'):
        from .tool_browser import ToolBrowser
        dialog = ToolBrowser(self, category=category if isinstance(category, str) else 'all')
        selected = []
        dialog.tool_selected.connect(selected.append)
        if dialog.exec() == QDialog.Accepted and selected:
            self.diagnostic_action(selected[0])

    def update_edit_history(self):
        if hasattr(self, 'workspace_header'):
            self.workspace_header.refresh_history()

    def diagnostic_action(self, action):
        if action == 'stamp':
            self.insert_stamp()
        elif action == 'sign_draw':
            self.open_sign_draw()
        elif action == 'save_as':
            self.save_as()
        elif action == 'multi_tool':
            self.toggle_multi_tool(True)
        elif action == 'pdf_info':
            self.open_pdf_info()
        elif action == 'pipeline':
            self.editing_toggle.setChecked(True)
            self.workspace_header.editing_panel.tabs.setCurrentIndex(1)
        elif action == 'merge':
            self.run_library_merge()
        elif action in {'convert_to_pdf', 'images_to_pdf'}:
            self.run_library_convert()
        elif action in {'pdf_to_images', 'pdf_to_text'}:
            self.save_as()
        elif action == 'compare_docs':
            from .diff_ui import DiffDialog
            DiffDialog(self, before=self.path).exec()
        elif action == 'search_docs':
            from .search_ui import SearchDialog
            SearchDialog(self).exec()
        elif action == 'summary':
            if self.path is None:
                return
            self._start_quick_batch('summary', [str(self.path)], str(self.original_path.parent))
        elif action == 'annotate':
            self.start_slideshow()
        elif action == 'rename':
            name = self.suggested_name
            if name and Path(name).name == name and not any(c in name for c in '<>:"/\\|?*'):
                self.save_changes(suggested_name=name)
        elif action == 'presentation':
            self.start_slideshow()
        elif action == 'form':
            self.edit_form()
        elif action == 'copy_image':
            self.copy_page_image()
        elif action == 'viewmode':
            self.toggle_sidebar_mode()
        elif action == 'table':
            self.table_copy_button.setChecked(True)
            self.show_feedback(tr('복사할 표 전체를 마우스로 드래그해 주세요.'))
        else:
            self.open_advanced_dialog(action)

    def insert_stamp(self):
        if self.path is None:
            QMessageBox.information(self, tr('직인·서명 넣기'), tr('먼저 PDF 파일을 열어 주세요.'))
            return
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if self.stamp_editor is None:
            from .stamp_editor import StampEditor
            self.stamp_editor = StampEditor(self)
        self.stamp_editor.choose_image()

    def edit_form(self):
        if self.path is None:
            return
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        try:
            source = self.stage_current_preview(display=False)
            from .form_ui import FormDialog
            page = self.pages[self.page.value() - 1] if source == self.path else self.page.value() - 1
            dialog = FormDialog(source, page, self, password=self.password)
            dialog.saved.connect(self.load)
            dialog.exec()
        except Exception as error:
            QMessageBox.warning(self, tr('양식 입력 실패'), str(error))

    def finish_slideshow(self, slides):
        if Path(slides.path) not in (self.path, getattr(slides, 'viewer_draft_path', self.path)):
            self.load(slides.path, password=slides.password)
            self.page.setValue(min(slides.index + 1, self.count))
        else:
            self.page.setValue(slides.viewer_indices[slides.index] + 1)
        self.raise_()
        self.activateWindow()
        self.page.setFocus()

    def reset_thumbnails(self):
        self.thumbnails.blockSignals(True)
        self.thumbnails.clear()
        self.thumbnail_cache = set()
        for index, source_page in enumerate(self.pages):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, source_page)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            if self.thumbnail_mode:
                item.setSizeHint(QSize(128, 180))
                item.setTextAlignment(Qt.AlignHCenter)
            else:
                item.setText(tr('{page}페이지', page=index + 1))
                item.setToolTip(tr('원본 {page}페이지', page=source_page + 1))
                item.setSizeHint(QSize(170, 36))
            self.thumbnails.addItem(item)
        if self.pages:
            self.thumbnails.setCurrentRow(self.page.value() - 1)
        self.thumbnails.blockSignals(False)
        if self.thumbnail_mode and self.pages:
            self.thumbnail_timer.start(30)

    def toggle_sidebar_mode(self):
        self.thumbnail_mode = not self.thumbnail_mode
        self.sidebar_toggle.setChecked(True)
        self.left_tabs.setCurrentIndex(0)
        self.thumbnails.setFixedWidth(156 if self.thumbnail_mode else 190)
        self.thumbnails.setViewMode(QListView.IconMode if self.thumbnail_mode else QListView.ListMode)
        self.thumbnails.setIconSize(QSize(112, 144) if self.thumbnail_mode else QSize(0, 0))
        self.reset_thumbnails()
        self.update_sidebar_mode_action()

    def update_sidebar_mode_action(self):
        if hasattr(self, 'sidebar_mode_action'):
            self.sidebar_mode_action.setText(tr('목록 보기') if self.thumbnail_mode else tr('썸네일 보기'))
            self.sidebar_mode_action.setIcon(action_icon('list' if self.thumbnail_mode else 'thumbnail',
                                                       self.view_tools_button.menu()))

    def _mark_page_edit(self):
        self.dirty = True
        self.save_button.setEnabled(True)
        self.setWindowTitle(tr('* {v0} · 어잉PDF', v0=self.original_path.name))

    def move_current_page(self, delta):
        if self.path is None or not self.pages:
            return
        row = self.page.value() - 1
        target = row + delta
        if target < 0 or target >= self.count:
            return
        self.begin_edit()
        page_id = self.pages.pop(row)
        self.pages.insert(target, page_id)
        self._mark_page_edit()
        self.page.blockSignals(True)
        self.page.setValue(target + 1)
        self.page.blockSignals(False)
        self.reset_thumbnails()
        self.render()
        self.record_edit('페이지 순서 변경')

    def apply_sidebar_order(self, payload):
        order, current = payload
        order = list(order)
        if len(order) != self.count or set(order) != set(self.pages):
            self.reset_thumbnails()
            return
        if order == self.pages:
            return
        self.begin_edit()
        self.pages = order
        self._mark_page_edit()
        if current in self.pages:
            self.page.blockSignals(True)
            self.page.setValue(self.pages.index(current) + 1)
            self.page.blockSignals(False)
        self.reset_thumbnails()
        self.render()
        self.record_edit('페이지 순서 변경')

    def fill_thumbnails(self):
        if self.path is None or not self.thumbnail_mode or not self.thumbnails.count():
            return
        viewport = self.thumbnails.viewport()
        first = max(0, self.thumbnails.indexAt(QPoint(10, 10)).row())
        last = self.thumbnails.indexAt(QPoint(10, max(10, viewport.height() - 10))).row()
        if last < first:
            last = min(self.count - 1, first + max(2, viewport.height() // 174 + 1))
        visible = set(range(max(0, first - 1), min(self.count, last + 2)))
        distance = lambda row: max(first - row, row - last, 0)
        retained = set(sorted(self.thumbnail_cache | visible, key=distance)[:THUMBNAIL_CARD_LIMIT])
        for index in self.thumbnail_cache - retained:
            item = self.thumbnails.item(index)
            card = self.thumbnails.itemWidget(item)
            if card is not None:
                self.thumbnails.removeItemWidget(item)
                card.hide()
                card.setEnabled(False)
                card.deleteLater()
        self.thumbnail_cache.intersection_update(retained)
        pending = sorted((visible & retained) - self.thumbnail_cache)
        if not pending:
            return
        try:
            with open_pdf(self.path, self.password) as document:
                for index in pending[:4]:
                    page = document[self.pages[index]]
                    scale = min(112 / page.rect.width, 144 / page.rect.height)
                    raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                    image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                    card = QWidget()
                    card_layout = QVBoxLayout(card)
                    card_layout.setContentsMargins(3, 2, 3, 2)
                    card_layout.setSpacing(2)
                    header = QHBoxLayout()
                    header.addWidget(QLabel(str(index + 1)))
                    header.addStretch()
                    remove = QPushButton('×')
                    remove.setObjectName('deleteThumbnail')
                    remove.setToolTip(tr('{page}페이지 삭제', page=index + 1))
                    remove.setFixedSize(24, 24)
                    apply_style(remove, 'QPushButton {padding:0;background:#fff;color:#b33445;border:1px solid #e2d5d9;border-radius:5px;}')
                    remove.clicked.connect(lambda checked=False, row=index: self.stage_delete({row}))
                    header.addWidget(remove)
                    card_layout.addLayout(header)
                    thumbnail = QPushButton()
                    thumbnail.setObjectName('thumbnailPage')
                    thumbnail.setIcon(QIcon(QPixmap.fromImage(image)))
                    thumbnail.setIconSize(QSize(112, 144))
                    apply_style(thumbnail, 'QPushButton {padding:0;border:0;background:transparent;}')
                    thumbnail.clicked.connect(lambda checked=False, row=index: self.page.setValue(row + 1))
                    card_layout.addWidget(thumbnail)
                    self.thumbnails.setItemWidget(self.thumbnails.item(index), card)
                    self.thumbnail_cache.add(index)
            if len(pending) > 4:
                self.thumbnail_timer.start(30)
        except Exception:
            pass

    def choose_pdf(self):
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if not self.confirm_leave():
            return
        start_dir = str(self.original_path.parent) if self.original_path.parent.exists() else ''
        path, _ = QFileDialog.getOpenFileName(self, tr('PDF 열기'), start_dir, 'PDF (*.pdf)')
        if path:
            try:
                self.load(path)
            except PdfOpenCancelled:
                return
            except Exception as error:
                QMessageBox.warning(self, tr('PDF 열기 실패'), str(error))

    def load(self, path, password='', *, preview=False):
        if not preview and any(Path(path).resolve().is_relative_to(Path(owner.name).resolve())
                               for owner in self.preview_owners):
            raise ValueError(tr('미리보기 임시 PDF는 새 원본으로 열 수 없습니다. 사본을 저장한 뒤 열어 주세요.'))
        password, count = unlock_viewer_pdf(path, self, password)
        if self.stamp_editor is not None:
            self.stamp_editor.reset()
        self.password = password
        self.search_hit = None
        self.path, self.count = Path(path), count
        if not preview:
            self.original_path = self.path
            self.sniffer.stop()
            self.edit_history = None
            self.clear_previews()
            self.library_panel.add_paths([self.path])
            self.library_panel.highlight_active(self.path)
            self.left_tabs.setCurrentIndex(0)
        self.source_count = count
        self.sniffed_path = None
        self.suggested_name = ''
        self.sniffer.start(self.path)
        self.sniffed_path = self.path
        self.pages = list(range(count))
        self.dirty = False
        self.save_button.setEnabled(False)
        self.save_as_button.setEnabled(True)
        self.setWindowTitle(tr('{v0} · 어잉PDF', v0=self.path.name))
        self.page.blockSignals(True)
        self.page.setRange(1, count)
        self.page.setValue(1)
        self.page.setSuffix(f' / {count}')
        self.page.blockSignals(False)
        self.center_stack.setCurrentIndex(0)
        self.multitool_rail_button.setChecked(False)
        self._last_fit_render = None
        self.reset_thumbnails()
        self.render()
        if not preview:
            self.reset_edit_history()

    def capture_edit_state(self):
        from .edit_history import DraftState
        editor = self.stamp_editor
        stamps = editor.snapshot() if editor else ()
        selected = next((index for index, stamp in enumerate(editor.stamps)
                         if stamp is editor.selected), -1) if editor else -1
        return DraftState(self.path, self.password, self.source_count, tuple(self.pages),
                          stamps, selected, self.page.value(), self.dirty)

    def notify_edit_history(self):
        if hasattr(self, 'update_edit_history'):
            self.update_edit_history()

    def reset_edit_history(self):
        if self.path is None:
            return
        from .edit_history import EditHistory
        self.edit_history = EditHistory(self.capture_edit_state(), '문서 열기')
        self.notify_edit_history()

    def begin_edit(self):
        if self.edit_history and not self._history_restoring:
            self.edit_history.sync_presentation(self.capture_edit_state())

    def update_dirty_state(self):
        if self.edit_history:
            self.dirty = self.capture_edit_state() != self.edit_history.baseline
        else:
            self.dirty = bool(self.stamp_editor and self.stamp_editor.stamps) or self.pages != list(range(self.source_count))
        self.save_button.setEnabled(self.dirty)
        self.setWindowTitle(tr('* {v0} · 어잉PDF', v0=self.original_path.name) if self.dirty else
                            tr('{v0} · 어잉PDF', v0=self.original_path.name))
        self.notify_edit_history()

    def record_edit(self, label):
        if self._history_restoring or self.edit_history is None:
            return
        self.update_dirty_state()
        self.edit_history.push(self.capture_edit_state(), label)
        self._materialized_state = None
        self.collect_preview_owners()
        self.notify_edit_history()
        if not self.feedback_timer.isActive():
            self.restore_status()

    def collect_preview_owners(self):
        paths = {self.path} if self.path else set()
        if self.materialized_path:
            paths.add(self.materialized_path)
        if self.edit_history:
            paths.update(state.path for state in self.edit_history.retained_states if state.path)
        retained = []
        for owner in self.preview_owners:
            if any(path.resolve().is_relative_to(Path(owner.name).resolve()) for path in paths):
                retained.append(owner)
            else:
                try:
                    owner.cleanup()
                except OSError:
                    retained.append(owner)
        self.preview_owners[:] = retained
        if self.stamp_editor:
            self.stamp_editor.release_unused_images()

    def _restore_edit_state(self, state):
        with open_pdf(state.path, state.password) as document:
            if document.page_count != state.source_count or not state.pages or any(
                    type(page) is not int or not 0 <= page < document.page_count for page in state.pages):
                raise ValueError(tr('기록된 PDF 페이지를 복원할 수 없습니다. 현재 편집은 유지됩니다.'))
            document[state.pages[max(0, min(state.page - 1, len(state.pages) - 1))]].get_pixmap(matrix=pdf.Matrix(.1, .1))
        self._history_restoring = True
        try:
            self.path, self.password, self.source_count = state.path, state.password, state.source_count
            self.pages, self.count = list(state.pages), len(state.pages)
            self.search_hit = None
            self.sniffer.stop()
            self.sniffed_path = None
            self.suggested_name = ''
            self.page.blockSignals(True)
            self.page.setRange(1, self.count)
            self.page.setSuffix(f' / {self.count}')
            self.page.setValue(max(1, min(state.page, self.count)))
            self.page.blockSignals(False)
            if state.stamps and self.stamp_editor is None:
                from .stamp_editor import StampEditor
                self.stamp_editor = StampEditor(self)
            if self.stamp_editor:
                self.stamp_editor.restore(state.stamps, state.selected_index)
            self.dirty = state.dirty
            self.save_button.setEnabled(self.dirty)
            self.setWindowTitle(tr('* {v0} · 어잉PDF', v0=self.original_path.name) if self.dirty else
                                tr('{v0} · 어잉PDF', v0=self.original_path.name))
            self._last_fit_render = None
            self.reset_thumbnails()
            self.render()
            self.update_more_features()
        finally:
            self._history_restoring = False

    def restore_history(self, position):
        if self.stamp_editor:
            self.stamp_editor.finish_gesture()
        history = self.edit_history
        if history is None or type(position) is not int or not 0 <= position < len(history.entries):
            return False
        if position == history.position:
            return True
        previous = self.capture_edit_state()
        try:
            self._restore_edit_state(history.entries[position].state)
        except Exception as error:
            if self.capture_edit_state() != previous:
                self._restore_edit_state(previous)
            QMessageBox.warning(self, tr('변경 복원 실패'), str(error))
            return False
        history.position = position
        self.materialized_path = None
        self._materialized_state = None
        self.collect_preview_owners()
        self.notify_edit_history()
        self.show_feedback(tr('변경 내역을 복원했습니다: {operation}', operation=tr(history.entries[position].label)))
        return True

    def undo_edit(self):
        if self.stamp_editor:
            self.stamp_editor.finish_gesture()
        if self.edit_history and self.edit_history.can_undo:
            return self.restore_history(self.edit_history.position - 1)
        return False

    def redo_edit(self):
        if self.stamp_editor:
            self.stamp_editor.finish_gesture()
        if self.edit_history and self.edit_history.can_redo:
            return self.restore_history(self.edit_history.position + 1)
        return False

    def reset_edits(self):
        if self.stamp_editor:
            self.stamp_editor.finish_gesture()
        if not self.edit_history or self.capture_edit_state() == self.edit_history.baseline:
            return False
        previous = self.capture_edit_state()
        try:
            self._restore_edit_state(self.edit_history.baseline)
        except Exception as error:
            if self.capture_edit_state() != previous:
                self._restore_edit_state(previous)
            QMessageBox.warning(self, tr('변경 복원 실패'), str(error))
            return False
        self.record_edit('전체 변경 되돌리기')
        self.materialized_path = None
        self._materialized_state = None
        self.collect_preview_owners()
        self.show_feedback(tr('처음 연 PDF로 되돌렸습니다. 실행 취소로 편집을 다시 가져올 수 있습니다.'))
        return True

    def clear_previews(self):
        retained = []
        for owner in self.preview_owners:
            try:
                owner.cleanup()
            except OSError:
                retained.append(owner)
        self.preview_owners[:] = retained
        self.materialized_path = None
        self._materialized_state = None

    def apply_preview(self, path, password, owner, label=None):
        """Take ownership of a reviewed working copy without publishing a user file."""
        page = self.page.value()
        self.load(path, password, preview=True)
        self.preview_owners.append(owner)
        self.dirty = True
        self.save_button.setEnabled(True)
        self.page.setValue(min(page, self.count))
        self.setWindowTitle(tr('* {v0} · 어잉PDF', v0=self.original_path.name))
        self.status.setText(tr('미리보기가 적용됐습니다. 확인한 뒤 저장을 누르세요.'))
        self.record_edit(label or 'PDF 효과 적용')

    def stage_current_preview(self, *, display=True):
        if self.path is None:
            raise ValueError(tr('먼저 PDF 문서를 열어 주세요.'))
        if self.pages == list(range(self.source_count)) and not (self.stamp_editor and self.stamp_editor.stamps):
            return self.path
        state = self.capture_edit_state()
        if state == self._materialized_state and self.materialized_path and self.materialized_path.exists():
            target = self.materialized_path
            if display:
                page = self.page.value()
                self.load(target, self.password, preview=True)
                self.page.setValue(min(page, self.count))
                self.update_dirty_state()
            return target
        import tempfile
        owner = tempfile.TemporaryDirectory(prefix='eoing-preview-')
        try:
            target = Path(owner.name) / 'current.pdf'
            with open_pdf(self.path, self.password) as document:
                apply_page_order(document, self.pages)
                if self.stamp_editor:
                    self.stamp_editor.apply(document, self.pages)
                document.save(target, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_KEEP)
            if display:
                page = self.page.value()
                self.load(target, self.password, preview=True)
                self.page.setValue(min(page, self.count))
                self.dirty = True
                self.save_button.setEnabled(True)
                self.setWindowTitle(tr('* {v0} · 어잉PDF', v0=self.original_path.name))
            self.preview_owners.append(owner)
            self.materialized_path, self._materialized_state = target, state
            self.collect_preview_owners()
            return target
        except Exception:
            owner.cleanup()
            raise

    def show_search_result(self, result):
        import math
        from .semantic_search import fingerprint
        if self.path is None or Path(result['path']).resolve() != self.path.resolve():
            raise ValueError(tr('검색 결과와 열린 문서가 다릅니다.'))
        if fingerprint(self.path) != result['digest']:
            raise ValueError(tr('검색 후 문서가 변경되었습니다. 폴더를 다시 색인해 주세요.'))
        index = result['page']
        if type(index) is not int or index not in self.pages:
            raise ValueError(tr('검색 결과 페이지를 찾을 수 없습니다.'))
        coordinates = result['rect']
        if len(coordinates) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coordinates):
            raise ValueError(tr('검색 결과 영역이 올바르지 않습니다.'))
        with open_pdf(self.path, self.password) as document:
            area = pdf.Rect(coordinates)
            visible = area * document[index].rotation_matrix
            if area.is_empty or not document[index].rect.intersects(visible):
                raise ValueError(tr('검색 결과 영역이 페이지 밖에 있습니다.'))
        self.search_hit = (index, tuple(coordinates))
        self.page.setValue(self.pages.index(index) + 1)
        self.render()
        self.show_feedback(tr('검색한 내용이 표시된 영역입니다.'))

    def remove_pages(self):
        if self.path is None:
            return
        selection, accepted = QInputDialog.getText(self, tr('페이지 삭제'), tr('삭제할 페이지 (예: 3, 7-9)\n마지막에 저장을 눌러 변경을 저장하세요.'), text=str(self.page.value()))
        if not accepted or not selection.strip():
            return
        try:
            self.stage_delete(set(pages_from_text(selection, self.count)))
        except Exception as error:
            QMessageBox.warning(self, tr('페이지 삭제 실패'), str(error))

    def stage_delete(self, removed):
        if self.path is None:
            return
        from .license_ui import ensure_license
        if not ensure_license(self):
            return
        if len(removed) >= self.count:
            QMessageBox.warning(self, tr('페이지 삭제'), tr('한 페이지 이상 남겨 주세요.'))
            return
        selected = ', '.join(str(i + 1) for i in sorted(removed))
        answer = QMessageBox.question(self, tr('페이지 삭제 확인'), tr('{pages}페이지를 삭제할까요?\n저장 전까지 원본 파일은 변경되지 않습니다.', pages=selected), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.begin_edit()
        current_row = self.page.value() - 1
        current_page = self.pages[current_row]
        kept_before = sum(index not in removed for index in range(current_row))
        self.pages = [page for index, page in enumerate(self.pages) if index not in removed]
        self.count = len(self.pages)
        self._mark_page_edit()
        self.page.blockSignals(True)
        self.page.setRange(1, self.count)
        self.page.setSuffix(f' / {self.count}')
        self.page.setValue(self.pages.index(current_page) + 1 if current_page in self.pages
                           else min(kept_before + 1, self.count))
        self.page.blockSignals(False)
        self._last_fit_render = None
        self.reset_thumbnails()
        self.render()
        self.record_edit('페이지 삭제')

    def save_changes(self, *, suggested_name=None):
        if self.path is None:
            return True
        if not self.dirty and suggested_name is None:
            return True
        from .license_ui import ensure_license
        if not ensure_license(self):
            return False
        target, _ = QFileDialog.getSaveFileName(self, tr('추천 이름으로 사본 저장') if suggested_name else tr('편집한 PDF 저장'), str(self.original_path.with_name(suggested_name or self.original_path.stem + tr('_편집.pdf'))), 'PDF (*.pdf)')
        if not target:
            return False
        try:
            import tempfile
            from .jobs import publish
            target = Path(target)
            if any(target.resolve().is_relative_to(Path(owner.name)) for owner in self.preview_owners):
                raise ValueError(tr('미리보기 임시 폴더 밖에 저장해 주세요.'))
            if target.suffix.lower() != '.pdf':
                target = target.with_suffix('.pdf')
            if target.resolve() == self.path.resolve():
                raise ValueError(tr('원본 보존을 위해 다른 파일 이름을 선택해 주세요.'))
            with tempfile.TemporaryDirectory(prefix='eoing-viewer-') as temporary:
                result = Path(temporary) / 'edited.pdf'
                with open_pdf(self.path, self.password) as document:
                    apply_page_order(document, self.pages)
                    if self.stamp_editor is not None:
                        self.stamp_editor.apply(document, self.pages)
                    document.save(result, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_KEEP)
                with open_pdf(result, self.password) as check:
                    if check.page_count != len(self.pages):
                        raise ValueError(tr('저장한 페이지 수가 일치하지 않습니다.'))
                saved = publish(result, target.parent, target.name)
            current_page = self.page.value()
            self.load(saved, password=self.password)
            self.page.setValue(min(current_page, self.count))
            self.status.setText(tr('저장했어요: {file} · 원본 보존', file=saved.name))
            return True
        except Exception as error:
            QMessageBox.warning(self, tr('PDF 저장 실패'), str(error))
            return False

    def confirm_leave(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, tr('저장하지 않은 변경'), tr('저장하지 않은 변경 사항을 저장할까요?'), QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            return self.save_changes()
        return answer == QMessageBox.Discard

    def reject(self):
        self.close()

    def closeEvent(self, event):
        if self.slideshow is not None and self.slideshow.isVisible():
            self.slideshow.reject()
            if self.slideshow.isVisible():
                event.ignore()
                return
        if self.confirm_leave():
            self.thumbnail_timer.stop()
            self.fit_timer.stop()
            self.feedback_timer.stop()
            self.sniffer.stop()
            self.edit_history = None
            if self.stamp_editor:
                self.stamp_editor.reset()
            self.clear_previews()
            self.thumbnails.clear()
            self.thumbnail_cache.clear()
            self.canvas.clear()
            self.thumbnail_timer.stop()
            super().reject()
            from PySide6.QtWidgets import QApplication
            updater = getattr(QApplication.instance(), 'updater', None)
            if updater is not None and hasattr(updater, 'flush_on_close'):
                updater.flush_on_close()
            event.accept()
        else:
            event.ignore()

    def clear_scroll_landing(self, *_):
        self._wheel_bottom_page = None

    def _keep_previous_page_bottom(self, minimum, maximum):
        if self._wheel_bottom_page == self.page.value():
            self.scroll.verticalScrollBar().setValue(maximum)

    def scroll_page(self, delta):
        target = max(1, min(self.count, self.page.value() + delta))
        if target == self.page.value():
            return
        self._wheel_bottom_page = target if delta < 0 else None
        self.page.setValue(target)

    def _fit_target_bounds(self, page_size=None):
        """Reserve scrollbar extent only when rendered page height approaches viewport height."""
        bar_extent = max(
            self.scroll.verticalScrollBar().sizeHint().width(),
            self.style().pixelMetric(QStyle.PM_ScrollBarExtent),
            18,
        )
        outer_width = self.scroll.width() if self.scroll.width() > 0 else self.scroll.viewport().width() + bar_extent
        outer_height = self.scroll.height() if self.scroll.height() > 0 else self.scroll.viewport().height()
        frame = self.scroll.frameWidth() * 2
        avail_w = max(100, outer_width - frame - 30)
        avail_h = max(100, outer_height - frame - 24)
        pw, ph = page_size or getattr(self, 'visible_page_size', (1, 1))
        if pw > 0 and ph > 0 and self.zoom.currentIndex() == 0:
            if ph * (avail_w / pw) + 8 >= (outer_height - frame):
                avail_w = max(100, outer_width - frame - bar_extent - 30)
        return avail_w, avail_h

    def _fit_target_width(self):
        return self._fit_target_bounds()[0]

    def _fit_key(self):
        return (str(self.path), self.page.value(), self.zoom.currentIndex(), *self._fit_target_bounds())

    def render(self, *_):
        if self.path is None or not self.pages:
            return
        try:
            self.canvas.set_selecting(self.table_copy_button.isChecked())
            with open_pdf(self.path, self.password) as document:
                page = document[self.pages[self.page.value() - 1]]
                self.visible_page_size = (page.rect.width, page.rect.height)
                fit_w, fit_h = self._fit_target_bounds(self.visible_page_size)
                zoom_idx = self.zoom.currentIndex()
                if zoom_idx == 0:
                    scale = fit_w / page.rect.width
                elif zoom_idx == 1:
                    scale = min(fit_w / page.rect.width, fit_h / page.rect.height)
                else:
                    scale = int(self.zoom.currentText()[:-1]) / 100
                scale = min(scale, 5000 / max(page.rect.width, page.rect.height))
                self._last_fit_render = self._fit_key()
                raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                self.canvas.setPixmap(QPixmap.fromImage(image))
                self.canvas.resize(raster.width, raster.height)
                if self.stamp_editor is not None:
                    self.stamp_editor.refresh()
                self.canvas.set_search_highlight()
                if self.search_hit and self.search_hit[0] == self.pages[self.page.value() - 1]:
                    area = (pdf.Rect(self.search_hit[1]) * page.rotation_matrix) & page.rect
                    self.canvas.set_search_highlight(QRectF(
                        area.x0 / page.rect.width, area.y0 / page.rect.height,
                        area.width / page.rect.width, area.height / page.rect.height))
            self.previous.setEnabled(self.page.value() > 1)
            self.next.setEnabled(self.page.value() < self.count)
            self.move_up_button.setEnabled(self.page.value() > 1)
            self.move_down_button.setEnabled(self.page.value() < self.count)
            scrollbar = self.scroll.verticalScrollBar()
            if self._wheel_bottom_page == self.page.value():
                scrollbar.setValue(scrollbar.maximum())
            else:
                self._wheel_bottom_page = None
                scrollbar.setValue(0)
                highlight = self.canvas.search_highlight
                if highlight is not None:
                    self.scroll.ensureVisible(round(highlight.center().x() * self.canvas.width()),
                                              round(highlight.center().y() * self.canvas.height()), 30, 30)
            if not self.feedback_timer.isActive():
                self.restore_status()
            self.thumbnails.blockSignals(True)
            self.thumbnails.setCurrentRow(self.page.value() - 1)
            self.thumbnails.scrollToItem(self.thumbnails.currentItem())
            self.thumbnails.blockSignals(False)
            self.thumbnail_timer.start(30)
        except Exception as error:
            self.canvas.clear()
            self.canvas.set_search_highlight()
            self.status.setText(tr('페이지를 열지 못했습니다: {error}', error=tr(str(error))))

    def _schedule_fit_render(self):
        if self.path is None or not hasattr(self, 'scroll') or self.zoom.currentIndex() not in (0, 1):
            return
        if getattr(self, '_last_fit_render', None) != self._fit_key():
            self.fit_timer.start(30)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'thumbnail_container'):
            thumb_w = 224 if self.width() >= 900 else 164
            if self.thumbnail_container.width() != thumb_w:
                self.thumbnail_container.setFixedWidth(thumb_w)
                self.thumbnails.setFixedWidth(212 if thumb_w >= 220 else 156)
        if hasattr(self, 'workspace_header') and hasattr(self.workspace_header, 'editing_panel'):
            dock_w = 296 if self.width() >= 920 else 264
            self.workspace_header.editing_panel.set_panel_width(dock_w)
        self._schedule_fit_render()

    def showEvent(self, event):
        super().showEvent(event)
        if self.path is not None:
            self.fit_timer.start(0)
            if self.sniffed_path != self.path:
                self.sniffed_path = self.path
                self.sniffer.start(self.path)

    def adjust_zoom(self, direction, position=None):
        if self.path is None:
            return
        levels = [50, 75, 100, 125, 150, 200]
        zoom_idx = self.zoom.currentIndex()
        if zoom_idx == 0:
            current = 100 * self._fit_target_bounds()[0] / self.visible_page_size[0]
        elif zoom_idx == 1:
            fw, fh = self._fit_target_bounds()
            current = 100 * min(fw / self.visible_page_size[0], fh / self.visible_page_size[1])
        else:
            current = int(self.zoom.currentText()[:-1])
        candidates = [level for level in levels if level > current + 0.01] if direction > 0 else [level for level in levels if level < current - 0.01]
        if not candidates:
            return
        target = min(candidates) if direction > 0 else max(candidates)
        viewport = self.scroll.viewport()
        point = position or viewport.rect().center()
        canvas_point = self.canvas.mapFrom(viewport, point)
        x = canvas_point.x() / max(1, self.canvas.width())
        y = canvas_point.y() / max(1, self.canvas.height())
        self.zoom.setCurrentText(f'{target}%')
        self.scroll.horizontalScrollBar().setValue(round(x * self.canvas.width() - point.x()))
        self.scroll.verticalScrollBar().setValue(round(y * self.canvas.height() - point.y()))

    def eventFilter(self, watched, event):
        try:
            scroll = getattr(self, 'scroll', None)
            canvas = getattr(self, 'canvas', None)
            viewport = scroll.viewport() if scroll is not None else None
        except RuntimeError:
            return False
        if viewport is not None and watched in (viewport, canvas) and event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                pos = event.position().toPoint()
                if watched is canvas:
                    pos = canvas.mapTo(viewport, pos)
                self.adjust_zoom(1 if delta > 0 else -1, pos)
            event.accept()
            return True
        if viewport is not None and watched is viewport and event.type() == QEvent.Resize:
            self._schedule_fit_render()
        return super().eventFilter(watched, event)


class SlideShow(QDialog):
    """Keyboard and mouse presentation without changing the PDF."""
    page_changed = Signal()
    def __init__(self, path, page=0, parent=None, pages=None, password=''):
        super().__init__(parent)
        self.path = Path(path)
        self.password = password
        with open_pdf(path, self.password) as document:
            self.pages = list(pages) if pages is not None else list(range(document.page_count))
            self.count = len(self.pages)
        self.index = max(0, min(page, self.count - 1))
        self.blank = None
        self.presenter = None
        self.grid = None
        self.reveal_steps = []
        self.reveal_index = -1
        self.ink_by_slide = {}
        self.boards = {}
        self.viewer_indices = list(range(self.count))
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(lambda: self.advance(1))
        self.setWindowTitle(tr('어잉PDF · 슬라이드쇼'))
        # Audience chrome has a fixed dark palette, independent of the app theme.
        # Do not send document-stage colors through the legacy SDK color mapper.
        self.setProperty('eoingAudience', True)
        self.setStyleSheet('''
            QDialog, QLabel {background:#111827;color:#dbe5f5;border:0;}
            QPushButton, QComboBox {
                background:#263246;color:#ffffff;border:1px solid #64748b;
                border-radius:6px;padding:8px 16px;font-size:15px;font-weight:400;
            }
            QPushButton:hover, QComboBox:hover {background:#405170;}
            QPushButton:checked {background:#405170;border:2px solid #a8c7ff;}
            QPushButton:focus, QComboBox:focus {border:2px solid #a8c7ff;}
            QComboBox QAbstractItemView {
                background:#263246;color:#ffffff;
                selection-background-color:#405170;selection-color:#ffffff;
            }
        ''')
        self.setFocusPolicy(Qt.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        controls = QHBoxLayout()
        controls.setContentsMargins(12, 8, 12, 0)
        controls.addStretch()
        self.presenter_button = QPushButton(tr('발표자 화면'))
        set_action_icon(self.presenter_button, 'presenter')
        self.presenter_button.setAutoDefault(False)
        self.presenter_button.clicked.connect(lambda: self.show_presenter())
        controls.addWidget(self.presenter_button)
        self.ink_button = QPushButton(tr('판서 · P'))
        set_action_icon(self.ink_button, 'pen')
        self.ink_button.setCheckable(True)
        self.ink_button.setAutoDefault(False)
        self.ink_button.toggled.connect(lambda checked: self.canvas.toggle_ink() if hasattr(self, 'canvas') and checked != self.canvas.ink_enabled else None)
        controls.addWidget(self.ink_button)
        self.ink_tools = QComboBox()
        for label, tool in [(tr('펜 · P'), 'pen'), (tr('형광펜 · H'), 'highlight'), (tr('임시 펜 · Ctrl+P'), 'ghost'),
                            (tr('도형 보정 · Ctrl+D'), 'shape'), (tr('텍스트 · T'), 'text'), (tr('지우개 · E'), 'erase'),
                            (tr('선택·이동'), 'select'), (tr('직선'), 'line'), (tr('사각형'), 'rectangle'),
                            (tr('타원'), 'ellipse'), (tr('화살표'), 'arrow')]:
            self.ink_tools.addItem(label, tool)
        self.ink_tools.setToolTip(tr('형광펜: 텍스트 줄에 드래그 · 임시 펜: 3초 뒤 사라짐 · 도형: 원·사각형·화살표·별·체크 보정'))
        self.ink_tools.activated.connect(lambda _: self.select_ink_tool(self.ink_tools.currentData()))
        self.bake_button = QPushButton(tr('판서 저장'))
        set_action_icon(self.bake_button, 'save')
        self.bake_button.setAutoDefault(False)
        self.bake_button.clicked.connect(self.bake_annotations)
        controls.addWidget(self.bake_button)
        self.exit_button = QPushButton(tr('전체화면 종료 · Esc'))
        set_action_icon(self.exit_button, 'close')
        self.exit_button.setAutoDefault(False)
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.exit_button.clicked.connect(self.reject)
        controls.addWidget(self.exit_button)
        layout.addLayout(controls)
        from .ink_toolbar import InkToolbar
        self.ink_toolbar = InkToolbar(self)
        layout.addWidget(self.ink_toolbar)
        from .presentation_canvas import PresentationCanvas
        self.canvas = PresentationCanvas()
        self.canvas.text_edit_started.connect(self.click_timer.stop)
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setMinimumSize(1, 1)
        self.canvas.installEventFilter(self)
        layout.addWidget(self.canvas, 1)
        self.hint = QLabel()
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.installEventFilter(self)
        layout.addWidget(self.hint)
        native_ink = self.canvas.enable_native_ink()
        if native_ink is not None:
            native_ink.failed.connect(lambda error: self.hint.setText(
                tr('고속 판서를 시작하지 못해 기본 판서로 전환했습니다. ') + error))

    def bake_annotations(self):
        if not self.canvas.commit_text():
            return False
        self.stash_surface()
        if not self.has_ink():
            QMessageBox.information(self, tr('판서 저장'), tr('저장할 판서가 없습니다.'))
            return False
        original = getattr(self.parentWidget(), 'original_path', self.path)
        target, _ = QFileDialog.getSaveFileName(self, tr('판서 PDF 저장'),
                                                str(original.with_name(original.stem + tr('_판서.pdf'))),
                                                'PDF (*.pdf)')
        if not target:
            return False
        target = Path(target)
        if any(target.resolve().is_relative_to(Path(owner.name)) for owner in getattr(self.parentWidget(), 'preview_owners', [])):
            QMessageBox.warning(self, tr('판서 저장'), tr('미리보기 임시 폴더 밖에 저장해 주세요.'))
            return False
        if target.suffix.lower() != '.pdf':
            target = target.with_suffix('.pdf')
        if target.resolve() == self.path.resolve() or target.exists():
            QMessageBox.warning(self, tr('판서 저장'), tr('원본 또는 기존 파일은 덮어쓸 수 없습니다.'))
            return False
        try:
            from .presentation_ink import save_presentation_ink, board_order
            saved_boards = board_order(self.boards, self.count)
            save_presentation_ink(self.path, target, self.pages, self.ink_by_slide, self.password, self.boards)
            mapping = []
            next_index = 0
            for slide in range(self.count):
                if slide == self.index:
                    next_index = len(mapping)
                mapping.append(self.viewer_indices[slide])
                for key in saved_boards:
                    if key[0] == slide:
                        if slide == self.index and key[1] == self.blank:
                            next_index = len(mapping)
                        mapping.append(self.viewer_indices[slide])
            self.viewer_indices = mapping
            self.index = next_index
            self.count = len(mapping)
            self.blank = None
            self.boards.clear()
            # Continue from the saved document so another save cannot lose
            # previously committed ink or restore deleted viewer pages.
            self.path = target
            self.pages = list(range(self.count))
            self.ink_by_slide.clear()
            self.canvas.set_ink([])
            self.canvas.reset_history()
            if self.grid is not None:
                self.grid.reject()
                self.grid.deleteLater()
                self.grid = None
            self.ink_button.setChecked(False)
            self.render()
            self.page_changed.emit()
            QMessageBox.information(self, tr('판서 저장 완료'), tr('{file}으로 저장했습니다.', file=target.name))
            return True
        except Exception as error:
            QMessageBox.warning(self, tr('판서 저장 실패'), str(error))
            return False

    def has_ink(self):
        from .ink_stroke import permanent
        return any(permanent(stroke) for strokes in
                   [self.canvas.ink_strokes, *self.ink_by_slide.values(),
                    *(board["strokes"] for board in self.boards.values())] for stroke in strokes)

    def select_ink_tool(self, tool):
        self.canvas.set_tool(tool)
        self.ink_tools.setCurrentIndex(self.ink_tools.findData(tool))
        self.ink_button.setChecked(True)

    def done(self, result):
        self.click_timer.stop()
        if not self.canvas.commit_text():
            return
        if self.has_ink():
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr('저장하지 않은 판서'))
            dialog.setText(tr('발표 중 작성한 판서를 저장할까요?'))
            save = dialog.addButton(tr('저장'), QMessageBox.AcceptRole)
            discard = dialog.addButton(tr('저장하지 않음'), QMessageBox.DestructiveRole)
            cancel = dialog.addButton(tr('취소'), QMessageBox.RejectRole)
            dialog.setDefaultButton(save)
            dialog.setEscapeButton(cancel)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is save:
                if not self.bake_annotations():
                    return
            elif clicked is not discard:
                return
        self.ink_toolbar.stop_capture(restore=False)
        self.canvas.set_ink([])
        self.canvas.reset_history()
        self.ink_by_slide.clear()
        self.boards.clear()
        self.canvas.clear()
        super().done(result)

    def render(self):
        try:
            if self.blank:
                self.canvas.mask_suspended = False
                self.canvas.board_mode = True
                width, height = self.boards[(self.index, self.blank)]['size']
                self.canvas.page_size = (width, height)
                self.canvas.text_lines = []
                ratio = self.devicePixelRatioF()
                scale = min(max(1, self.canvas.width()) / width, max(1, self.canvas.height()) / height)
                pixmap = QPixmap(max(1, round(width * scale * ratio)), max(1, round(height * scale * ratio)))
                pixmap.setDevicePixelRatio(ratio)
                self.canvas.setStyleSheet('background:' + self.blank + ';')
                self.canvas.ink_width = 2.5 * scale
                pixmap.fill(Qt.black if self.blank == 'black' else Qt.white)
                self.canvas.setPixmap(pixmap)
                name = tr('검은 칠판') if self.blank == 'black' else tr('흰 칠판')
                self.hint.setText(tr('{board} · P: 필기 · T: 텍스트 · B/W: 칠판 전환 · Space: 슬라이드 복귀 · 저장 시 별도 페이지 추가', board=name))
                return
            self.canvas.mask_suspended = False
            self.canvas.board_mode = False
            self.canvas.setStyleSheet('')
            with open_pdf(self.path, self.password) as document:
                page = document[self.pages[self.index]]
                # Display coordinates account for the PDF page's intrinsic rotation.
                self.canvas.page_size = (page.rect.width, page.rect.height)
                self.canvas.text_lines = []
                text = page.get_text('dict', flags=pdf.TEXTFLAGS_DICT & ~pdf.TEXT_PRESERVE_IMAGES)
                for block in text['blocks']:
                    for line in block.get('lines', []):
                        if any(span.get('text', '').strip() for span in line['spans']):
                            rect = (pdf.Rect(line['bbox']) * page.rotation_matrix) & page.rect
                            if not rect.is_empty:
                                self.canvas.text_lines.append(QRectF(rect.x0 / page.rect.width, rect.y0 / page.rect.height,
                                                                   rect.width / page.rect.width, rect.height / page.rect.height))
                ends = []
                for block in page.get_text('blocks'):
                    if block[6] == 0 and block[4].strip():
                        rect = pdf.Rect(block[:4]) * page.rotation_matrix
                        ends.append(min(1.0, max(0.0, (rect.y1 + 8) / page.rect.height)))
                self.reveal_steps = sorted(set(round(value, 4) for value in ends))
                ratio = self.devicePixelRatioF()
                scale = min(max(1, self.canvas.width()) / page.rect.width,
                            max(1, self.canvas.height()) / page.rect.height) * ratio
                scale = min(scale, 5000 / max(page.rect.width, page.rect.height))
                raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                image = QImage(raster.samples, raster.width, raster.height, raster.stride, QImage.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(image)
                pixmap.setDevicePixelRatio(ratio)
                self.canvas.setPixmap(pixmap)
                self.canvas.ink_width = 2.5 * pixmap.deviceIndependentSize().width() / page.rect.width
            self.hint.setText(tr('{page} / {total}   ·   Space: 문단 순서로 공개   ·   → / 클릭: 다음   ·   G: 페이지 목록   ·   Esc: 종료', page=self.index + 1, total=self.count))
        except Exception as error:
            self.canvas.clear()
            self.hint.setText(tr('페이지를 열지 못했습니다: {error} · Esc: 종료', error=tr(str(error))))

    def advance(self, delta):
        self.click_timer.stop()
        index = max(0, min(self.index + delta, self.count - 1))
        if index != self.index:
            if not self.canvas.commit_text():
                return
            self.stash_surface()
            self.index = index
            self.canvas.set_ink(self.ink_by_slide.setdefault(index, []))
            self.blank = None
            self.reveal_index = -1
            self.canvas.reveal_fraction = 1.0
            self.render()
            self.page_changed.emit()

    def stash_surface(self):
        if self.blank:
            self.boards[(self.index, self.blank)]['strokes'] = self.canvas.ink_strokes
        else:
            self.ink_by_slide[self.index] = self.canvas.ink_strokes

    def set_blank(self, color):
        if color not in ('black', 'white'):
            raise ValueError(tr('칠판 색상이 올바르지 않습니다.'))
        self.click_timer.stop()
        if not self.canvas.commit_text():
            return
        self.stash_surface()
        self.blank = None if self.blank == color else color
        if self.blank:
            board = self.boards.setdefault((self.index, self.blank), {
                'size': (720.0, 720.0 * max(1, self.canvas.height()) / max(1, self.canvas.width())),
                'strokes': []})
            self.canvas.set_ink(board['strokes'])
        else:
            self.canvas.set_ink(self.ink_by_slide.setdefault(self.index, []))
        self.render()

    def reveal_next(self):
        if self.blank:
            self.set_blank(self.blank)
            return
        if len(self.reveal_steps) <= 1 or self.reveal_index >= len(self.reveal_steps) - 1:
            self.advance(1)
            return
        self.reveal_index += 1
        self.canvas.reveal_fraction = (1.0 if self.reveal_index == len(self.reveal_steps) - 1
                                       else self.reveal_steps[self.reveal_index])
        self.canvas.update()

    def show_grid(self):
        from .slide_grid import SlideGrid
        if self.grid is None:
            self.grid = SlideGrid(self)
        self.grid.list.setCurrentRow(self.index)
        self.grid.show()
        self.grid.raise_()
        self.grid.activateWindow()

    def show_presenter(self, screen=None):
        from .presenter import PresenterHud
        if self.presenter is None:
            self.presenter = PresenterHud(self)
        if screen is not None:
            self.presenter.winId()
            self.presenter.windowHandle().setScreen(screen)
            self.presenter.move(screen.availableGeometry().topLeft())
        self.presenter.show()
        self.presenter.raise_()
        self.presenter.activateWindow()

    def keyPressEvent(self, event):
        key = event.key()
        if event.modifiers() & Qt.ControlModifier and key == Qt.Key_Z:
            self.canvas.redo_ink() if event.modifiers() & Qt.ShiftModifier else self.canvas.undo_ink()
        elif event.modifiers() & Qt.ControlModifier and key == Qt.Key_Y:
            self.canvas.redo_ink()
        elif event.modifiers() & Qt.ControlModifier and key == Qt.Key_V:
            self.ink_toolbar.paste()
        elif key == Qt.Key_Delete:
            self.canvas.delete_selected()
        elif key == Qt.Key_E:
            self.select_ink_tool('erase')
        elif key in (Qt.Key_Escape, Qt.Key_F5):
            self.reject()
        elif key == Qt.Key_B:
            self.set_blank('black')
        elif key == Qt.Key_W:
            self.set_blank('white')
        elif key == Qt.Key_G:
            self.show_grid()
        elif key == Qt.Key_S:
            self.canvas.toggle_spotlight()
        elif key == Qt.Key_L and event.modifiers() & Qt.ControlModifier:
            self.canvas.toggle_laser()
        elif key == Qt.Key_T:
            self.select_ink_tool('text')
        elif key == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            self.select_ink_tool('shape')
        elif key == Qt.Key_P and event.modifiers() & Qt.ControlModifier:
            self.select_ink_tool('ghost')
        elif key == Qt.Key_H:
            self.select_ink_tool('highlight')
        elif key == Qt.Key_P and self.canvas.ink_tool != 'pen':
            self.select_ink_tool('pen')
        elif key == Qt.Key_P:
            self.canvas.toggle_ink()
            if hasattr(self, 'ink_button'):
                self.ink_button.setChecked(self.canvas.ink_enabled)
        elif key == Qt.Key_Space and event.modifiers() & Qt.ShiftModifier:
            self.advance(-1)
        elif key == Qt.Key_Space:
            self.reveal_next()
        elif key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown, Qt.Key_Return, Qt.Key_Enter):
            self.advance(1)
        elif key in (Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp, Qt.Key_Backspace):
            self.advance(-1)
        elif key == Qt.Key_Home:
            self.advance(-self.count)
        elif key == Qt.Key_End:
            self.advance(self.count)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.advance(1)
        elif event.button() == Qt.RightButton:
            self.advance(-1)

    def eventFilter(self, watched, event):
        if watched is self.canvas and event.type() == QEvent.MouseButtonDblClick:
            self.click_timer.stop()
            return False
        if event.type() == QEvent.MouseButtonPress:
            if watched is self.canvas and self.canvas.ink_enabled and event.button() == Qt.LeftButton:
                return False
            if watched is self.canvas and event.button() == Qt.LeftButton and self.canvas.page_rect().contains(event.position()):
                point = self.canvas._normalized(event.position())
                if not any(rect.contains(point) for rect in self.canvas.text_lines):
                    self.click_timer.start(QGuiApplication.styleHints().mouseDoubleClickInterval())
                    return True
            self.click_timer.stop()
            self.mousePressEvent(event)
            return True
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.render()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'canvas'):
            self.render()
