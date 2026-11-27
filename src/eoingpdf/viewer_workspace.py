"""Task-focused Stirling-style reader chrome; editing history belongs to the viewer draft."""
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QMenu,
    QMenuBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .action_icons import action_icon, set_action_icon
from .inline_tools import RightToolsDock
from .localization import tr
from .sdk_theme import apply_style


def action_menu(parent):
    menu = QMenu(parent)
    apply_style(menu, 'QMenu::item:selected {background:#416ae6;color:white;}')
    return menu


class WorkspaceHeader(QWidget):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.setObjectName('workspaceHeader')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        def button(text, callback, icon, name=''):
            result = QPushButton(tr(text))
            result.setAutoDefault(False)
            result.setObjectName(name)
            result.setAccessibleName(tr(text))
            result.setToolTip(tr(text))
            set_action_icon(result, icon)
            result.clicked.connect(callback)
            return result

        def show_home():
            if not getattr(viewer, 'path', None):
                viewer.show_empty_home()
                return
            parent = viewer.parentWidget()
            if parent is None:
                viewer.show_empty_home()
                return
            if not viewer.close():
                return
            parent.show()
            parent.raise_()
            parent.activateWindow()

        viewer.home_button = button('홈', show_home, 'open', 'homeAction')
        layout.addWidget(viewer.home_button)

        viewer.sidebar_toggle = QPushButton(self)
        viewer.sidebar_toggle.setCheckable(True)
        viewer.sidebar_toggle.toggled.connect(lambda visible: viewer.thumbnail_container.setVisible(visible))
        viewer.sidebar_toggle.hide()

        viewer.editing_toggle = QPushButton(self)
        viewer.editing_toggle.setCheckable(True)
        viewer.editing_toggle.setChecked(True)
        viewer.editing_toggle.hide()

        menu_bar = QMenuBar(self)
        self.menu_bar = menu_bar
        self._menus = []
        menu_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        file_entries = (
            ('PDF 열기', viewer.choose_pdf),
            ('라이브러리에 추가', lambda: viewer.library_panel.choose_files()),
            ('사본 저장', viewer.save_changes),
            ('다른 이름으로 저장 · 변환', viewer.save_as),
            ('PDF 상세 정보 · 검사', viewer.open_pdf_info),
            ('닫기', viewer.close),
        )
        edit_entries = (
            ('실행 취소', viewer.undo_edit),
            ('다시 실행', viewer.redo_edit),
            ('변경 내역', viewer.open_history_dialog),
            ('페이지 멀티툴', lambda: viewer.toggle_multi_tool()),
            ('시계 90° 회전', lambda: viewer.quick_rotate(90)),
            ('페이지 삭제', viewer.remove_pages),
        )
        view_entries = (
            ('페이지 목록', lambda: viewer.sidebar_toggle.toggle()),
            ('도구 목록 표시', lambda: viewer.editing_toggle.toggle()),
            ('문서 라이브러리', lambda: viewer.open_library_tab()),
            ('너비 맞춤', lambda: viewer.zoom.setCurrentIndex(0)),
            ('페이지 맞춤', lambda: viewer.zoom.setCurrentIndex(1)),
        )
        window_entries = (
            ('슬라이드쇼 · F5', viewer.start_slideshow),
            ('두 문서 비교', lambda: viewer.diagnostic_action('compare_docs')),
            ('문서 내용 검색', lambda: viewer.diagnostic_action('search_docs')),
            ('작은 창에 파일 모으기', lambda: viewer.open_staging_dock()),
            ('단축키 안내 · F1', viewer.open_shortcuts_dialog),
        )

        for title, mnemonic, entries in (
            ('파일', 'F', file_entries),
            ('편집', 'E', edit_entries),
            ('보기', 'V', view_entries),
            ('창', 'W', window_entries),
        ):
            menu = menu_bar.addMenu(f'{tr(title)}(&{mnemonic})')
            self._menus.append(menu)
            for label, callback in entries:
                menu.addAction(tr(label)).triggered.connect(callback)
        layout.addWidget(menu_bar)

        # Prominent strength actions: Slideshow & Stamp/Sign
        viewer.slideshow_button = button('슬라이드쇼 · F5', viewer.start_slideshow, 'play', 'slideshowAction')
        viewer.slideshow_button.setToolTip(tr('현재 페이지부터 전체 화면으로 발표하고 판서합니다. · F5'))
        layout.addWidget(viewer.slideshow_button)

        viewer.stamp_button = button('직인·서명 넣기', viewer.insert_stamp, 'stamp', 'insertStamp')
        viewer.stamp_button.setToolTip(tr('직인 이미지·서명 그리기로 흰 배경을 자동 제거하고 배치합니다.'))
        layout.addWidget(viewer.stamp_button)

        viewer.more_features_menu = action_menu(viewer)
        layout.addStretch(1)

        viewer.save_as_button = button('다른이름 저장', viewer.save_as, 'export', 'saveAsAction')
        viewer.save_as_button.setToolTip(tr('다른 파일명 또는 확장자(PDF, 이미지, TXT, HTML, MD 등)로 저장 · Ctrl+Shift+S'))
        layout.addWidget(viewer.save_as_button)

        viewer.save_button = button('사본 저장', viewer.save_changes, 'save', 'saveCopyAction')
        viewer.save_button.setToolTip(tr('현재 화면의 변경을 새 PDF로 저장합니다. · Ctrl+S'))
        viewer.save_button.setEnabled(False)
        layout.addWidget(viewer.save_button)

        viewer.close_button = button('닫기', viewer.close, 'close')
        layout.addWidget(viewer.close_button)

        viewer.open_button = viewer.home_button
        self._compact_buttons = [
            (viewer.home_button, tr('홈')),
            (viewer.close_button, tr('닫기')),
            (viewer.save_button, tr('사본 저장')),
            (viewer.save_as_button, tr('다른이름 저장')),
            (viewer.stamp_button, tr('직인·서명 넣기')),
            (viewer.slideshow_button, tr('슬라이드쇼 · F5')),
        ]

        # Build Stirling-style RightToolsDock with inline tool cards and Pipelines
        self.editing_panel = RightToolsDock(viewer)

        page_menu = action_menu(viewer.page_tools_button)
        for text, callback, icon in (
            ('페이지 멀티툴 편집기', lambda: viewer.toggle_multi_tool(True), 'thumbnail'),
            ('페이지 삭제', viewer.remove_pages, 'delete'),
            ('앞으로 이동', lambda: viewer.move_current_page(-1), 'up'),
            ('뒤로 이동', lambda: viewer.move_current_page(1), 'down'),
            ('페이지 정리 도구 보기', lambda: viewer.show_all_tools('pages'), 'pages'),
        ):
            page_menu.addAction(action_icon(icon, page_menu), tr(text)).triggered.connect(callback)
        viewer.move_up_button = page_menu.actions()[2]
        viewer.move_down_button = page_menu.actions()[3]
        viewer.page_tools_button.setMenu(page_menu)

        menu = action_menu(viewer.view_tools_button)
        viewer.copy_image_button = menu.addAction(action_icon('image', menu), tr('페이지 이미지 복사'))
        viewer.copy_image_button.triggered.connect(viewer.copy_page_image)
        viewer.table_copy_button = menu.addAction(action_icon('table', menu), tr('표 드래그 복사'))
        viewer.table_copy_button.setCheckable(True)
        viewer.table_copy_button.toggled.connect(viewer.canvas.set_selecting)
        viewer.sidebar_mode_action = menu.addAction(action_icon('list', menu), '')
        viewer.sidebar_mode_action.triggered.connect(viewer.toggle_sidebar_mode)
        viewer.recommended_name_action = menu.addAction(action_icon('rename', menu), tr('제목으로 파일명 추천'))
        viewer.recommended_name_action.setVisible(False)
        viewer.recommended_name_action.triggered.connect(lambda: viewer.diagnostic_action('rename'))
        viewer.view_tools_button.setMenu(menu)

        viewer.editing_toggle.toggled.connect(self.editing_panel.setVisible)
        viewer.editing_toggle.setAccessibleName(tr('도구 목록 표시'))

        apply_style(self, '''
            QWidget#workspaceHeader {background:#ffffff; border-bottom:1px solid #e2e7ef; padding:2px 4px;}
            QPushButton {background:#ffffff; border:0; padding:6px 10px; border-radius:7px;}
            QPushButton:hover {background:#f1f5fb;}
            QPushButton:checked {background:#dbe6ff;}
            QPushButton#slideshowAction {border:1.5px solid #416ae6;}
            QPushButton#slideshowAction:hover {background:#dbe6ff;}
            QPushButton#insertStamp {border:1.5px solid #458475;}
            QPushButton#insertStamp:hover {background:#ecf6f2;}
            QPushButton#saveAsAction {border:1px solid #c6d3e6;}
        ''')

        from PySide6.QtCore import Qt
        for key, callback in (
            ('Ctrl+Z', viewer.undo_edit),
            ('Ctrl+Y', viewer.redo_edit),
            ('Ctrl+Shift+Z', viewer.redo_edit),
            ('Ctrl+Shift+T', viewer.show_all_tools),
            ('Ctrl+K', self.editing_panel.focus_search),
            ('Ctrl+Shift+S', viewer.save_as),
        ):
            shortcut = QShortcut(QKeySequence(key), viewer)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
        self.refresh_history()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for button, label in self._compact_buttons:
            button.setText(label)
        for button, _label in self._compact_buttons:
            if self.layout().sizeHint().width() <= self.width():
                break
            button.setText('')

    def refresh_history(self):
        viewer = self.viewer
        history = getattr(viewer, 'edit_history', None)
        viewer.undo_button.setEnabled(bool(history and history.can_undo))
        viewer.redo_button.setEnabled(bool(history and history.can_redo))
        viewer.history_button.setEnabled(bool(history and (history.can_undo or history.can_redo or viewer.dirty)))
        viewer.undo_button.setToolTip(
            tr('실행 취소: {action} · Ctrl+Z', action=tr(history.undo_label))
            if history and history.can_undo else tr('실행 취소 · Ctrl+Z')
        )
        viewer.redo_button.setToolTip(
            tr('다시 실행: {action} · Ctrl+Y', action=tr(history.redo_label))
            if history and history.can_redo else tr('다시 실행 · Ctrl+Y')
        )
        if history:
            viewer.history_button.setText(tr('변경 내역 · {count}', count=history.position))


class NavigationStrip(QWidget):
    """Stirling-style slim left activity rail for thumbnails, library, multi-tool, and utilities."""

    def __init__(self, viewer):
        super().__init__(viewer)
        self.setObjectName('navigationStrip')
        self.setFixedWidth(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 5, 4, 5)
        layout.setSpacing(4)

        def rail_btn(icon_name, tooltip, checkable=False):
            btn = QPushButton(self)
            btn.setFixedSize(30, 30)
            btn.setCheckable(checkable)
            set_action_icon(btn, icon_name)
            btn.setToolTip(tr(tooltip))
            btn.setAccessibleName(tr(tooltip))
            layout.addWidget(btn)
            return btn

        button = rail_btn('thumbnail', '페이지 목록', checkable=True)
        button.toggled.connect(viewer.sidebar_toggle.setChecked)
        viewer.sidebar_toggle.toggled.connect(button.setChecked)
        viewer.sidebar_toggle.hide()
        viewer.thumbnail_rail_button = button

        viewer.library_rail_button = rail_btn('open', 'PDF 보관함')
        viewer.library_rail_button.clicked.connect(viewer.open_library_tab)

        viewer.multitool_rail_button = rail_btn('pages', '페이지 멀티툴 편집기 · Ctrl+M', checkable=True)
        viewer.multitool_rail_button.clicked.connect(lambda checked: viewer.toggle_multi_tool(checked))

        viewer.compare_rail_button = rail_btn('table', '두 문서 비교')
        viewer.compare_rail_button.clicked.connect(lambda: viewer.diagnostic_action('compare_docs'))

        viewer.search_rail_button = rail_btn('search', '폴더 내 문서 검색 · Ctrl+F')
        viewer.search_rail_button.clicked.connect(lambda: viewer.diagnostic_action('search_docs'))

        viewer.pipeline_rail_button = rail_btn('tools', '자동화 파이프라인')
        viewer.pipeline_rail_button.clicked.connect(lambda: viewer.diagnostic_action('pipeline'))

        layout.addStretch(1)

        viewer.shortcuts_rail_button = rail_btn('list', '단축키 안내 · F1')
        viewer.shortcuts_rail_button.clicked.connect(viewer.open_shortcuts_dialog)

        def toggle_theme():
            controller = getattr(QApplication.instance(), 'eoing_theme', None)
            if controller is not None:
                controller.set_preference('light' if controller.mode == 'dark' else 'dark')

        viewer.theme_rail_button = rail_btn('presenter', '밝은/어두운 테마 전환')
        viewer.theme_rail_button.clicked.connect(toggle_theme)

        viewer.settings_rail_button = rail_btn('settings', '설정 · 업데이트')
        viewer.settings_rail_button.clicked.connect(viewer.open_settings_dialog)

        apply_style(self, '''
            QWidget#navigationStrip {background:#ffffff; border-right:1px solid #e2e7ef;}
            QPushButton {background:#ffffff; border:1px solid #e2e7ef; border-radius:8px; padding:4px;}
            QPushButton:hover {background:#f1f5fb; border-color:#c6d3e6;}
            QPushButton:checked {background:#edf2ff; border-color:#7c9dfa;}
        ''')


class HistoryDialog(QDialog):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.setWindowTitle(tr('변경 내역'))
        self.resize(460, 420)
        layout = QVBoxLayout(self)
        description = QLabel(tr('저장 전 작업을 선택해 그 상태로 돌아갈 수 있습니다.'))
        description.setWordWrap(True)
        layout.addWidget(description)
        self.entries = QListWidget()
        for index, entry in enumerate(viewer.edit_history.entries):
            prefix = tr('현재') if index == viewer.edit_history.position else str(index)
            self.entries.addItem(f'{prefix}  ·  {tr(entry.label)}')
        self.entries.setCurrentRow(viewer.edit_history.position)
        layout.addWidget(self.entries, 1)
        self.restore = QPushButton(tr('이 상태로 돌아가기'))
        set_action_icon(self.restore, 'restore')
        self.restore.setObjectName('restoreHistoryAction')
        self.restore.clicked.connect(self.restore_selected)
        layout.addWidget(self.restore)
        row = QHBoxLayout()
        reset = QPushButton(tr('모든 변경 되돌리기'))
        set_action_icon(reset, 'reset')
        reset.setEnabled(viewer.dirty)
        reset.clicked.connect(self.reset_all)
        row.addWidget(reset)
        close = QPushButton(tr('닫기'))
        set_action_icon(close, 'close')
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self.entries.currentRowChanged.connect(lambda index: self.restore.setEnabled(index != viewer.edit_history.position))
        self.restore.setEnabled(False)

    def restore_selected(self):
        index = self.entries.currentRow()
        if index >= 0 and self.viewer.restore_history(index):
            self.accept()

    def reset_all(self):
        if self.viewer.reset_edits():
            self.accept()
