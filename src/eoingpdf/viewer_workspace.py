"""Task-focused reader chrome; editing history belongs to the viewer draft."""
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                              QPushButton, QLabel, QMenu, QListWidget, QScrollArea,
                              QFrame, QMenuBar, QSizePolicy)
from .action_icons import action_icon, set_action_icon
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
        layout.setSpacing(2)

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
            parent = viewer.parentWidget()
            if not viewer.close():
                return
            if parent is None:
                from .app import Window
                from PySide6.QtWidgets import QApplication
                parent = Window()
                QApplication.instance()._eoing_home_window = parent
            parent.show()
            parent.raise_()
            parent.activateWindow()

        viewer.home_button = button('홈', show_home, 'open', 'homeAction')
        layout.addWidget(viewer.home_button)
        # Internal controls keep the existing page and panel state in one place;
        # the visible controls are the thumbnail rail and the View menu.
        viewer.sidebar_toggle = QPushButton(self)
        viewer.sidebar_toggle.setCheckable(True)
        viewer.sidebar_toggle.toggled.connect(lambda visible: viewer.thumbnails.setVisible(visible))
        viewer.sidebar_toggle.hide()
        viewer.editing_toggle = QPushButton(self)
        viewer.editing_toggle.setCheckable(True)
        viewer.editing_toggle.setChecked(True)
        viewer.editing_toggle.hide()

        menu_bar = QMenuBar(self)
        self.menu_bar = menu_bar
        self._menus = []
        menu_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        for title, entries in (
            ('파일', (('PDF 열기', viewer.choose_pdf), ('사본 저장', viewer.save_changes), ('닫기', viewer.close))),
            ('편집', (('실행 취소', viewer.undo_edit), ('다시 실행', viewer.redo_edit),
                    ('변경 내역', lambda: HistoryDialog(viewer).exec()))),
            ('보기', (('페이지 목록', lambda: viewer.sidebar_toggle.toggle()),
                    ('도구 목록 표시', lambda: viewer.editing_toggle.toggle()))),
            ('창', (('슬라이드쇼 · F5', viewer.start_slideshow),)),
        ):
            menu = menu_bar.addMenu(tr(title))
            self._menus.append(menu)
            for label, callback in entries:
                menu.addAction(tr(label)).triggered.connect(callback)
        layout.addWidget(menu_bar)
        viewer.slideshow_button = button('슬라이드쇼 · F5', viewer.start_slideshow, 'play', 'slideshowAction')
        viewer.slideshow_button.setToolTip(tr('현재 페이지부터 전체 화면으로 발표합니다.'))
        layout.addWidget(viewer.slideshow_button)
        viewer.stamp_button = button('직인·서명 넣기', viewer.insert_stamp, 'stamp', 'insertStamp')
        viewer.stamp_button.setToolTip(tr('JPG·PNG의 흰 배경을 제거하고 위치와 크기를 직접 조절합니다.'))
        layout.addWidget(viewer.stamp_button)
        help_bar = QMenuBar(self)
        self.help_bar = help_bar
        help_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        help_menu = help_bar.addMenu(tr('도움말'))
        self._menus.append(help_menu)
        help_menu.addAction(tr('설정·도움말')).triggered.connect(
            lambda: viewer.settings_button.showMenu())
        layout.addWidget(help_bar)
        viewer.tools_tab_button = button('도구', viewer.show_all_tools, 'tools', 'allTools')
        viewer.more_features_button = viewer.tools_tab_button
        viewer.more_features_button.setToolTip(tr('작업별로 찾거나 이름으로 도구를 검색합니다.'))
        viewer.more_features_menu = action_menu(viewer.more_features_button)
        layout.addWidget(viewer.tools_tab_button)
        layout.addStretch(1)
        viewer.save_button = button('사본 저장', viewer.save_changes, 'save', 'saveCopyAction')
        viewer.save_button.setToolTip(tr('현재 화면의 변경을 새 PDF로 저장합니다. · Ctrl+S'))
        viewer.save_button.setEnabled(False)
        layout.addWidget(viewer.save_button)
        viewer.close_button = button('닫기', viewer.close, 'close')
        layout.addWidget(viewer.close_button)
        # Kept as an alias for existing icon and accessibility health checks.
        viewer.open_button = viewer.home_button
        self._compact_buttons = [(viewer.home_button, tr('홈')), (viewer.close_button, tr('닫기')),
                                 (viewer.save_button, tr('사본 저장')), (viewer.tools_tab_button, tr('도구')),
                                 (viewer.slideshow_button, tr('슬라이드쇼 · F5')),
                                 (viewer.stamp_button, tr('직인·서명 넣기'))]

        def panel_button(text, callback, icon, name=''):
            result = button(text, callback, icon, name)
            row.addWidget(result)
            return result
        panel = QScrollArea(viewer)
        panel.setObjectName('toolsPanel')
        panel.setWidgetResizable(True)
        panel.setFixedWidth(210)
        panel.setFrameShape(QFrame.NoFrame)
        editing = QWidget()
        editing.setObjectName('editingActions')
        panel.setWidget(editing)
        self.editing_panel = panel
        row = QVBoxLayout(editing)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(2)
        heading = QLabel(tr('모든 도구'))
        heading.setObjectName('toolsHeading')
        row.addWidget(heading)
        viewer.panel_all_tools_button = panel_button('도구 검색', viewer.show_all_tools, 'search')
        viewer.panel_scan_button = panel_button('스캔·문자 인식', lambda: viewer.show_all_tools('scan'), 'scan')
        viewer.panel_security_button = panel_button('보안·개인정보', lambda: viewer.show_all_tools('security'), 'security')
        viewer.panel_export_button = panel_button('복사·내보내기', lambda: viewer.show_all_tools('export'), 'export')
        viewer.panel_optimize_button = panel_button('압축·복구', lambda: viewer.show_all_tools('optimize'), 'optimize')
        viewer.undo_button = panel_button('실행 취소', viewer.undo_edit, 'undo')
        viewer.redo_button = panel_button('다시 실행', viewer.redo_edit, 'redo')
        viewer.history_button = panel_button('변경 내역', lambda: HistoryDialog(viewer).exec(), 'history')
        viewer.form_button = panel_button('양식 입력', viewer.edit_form, 'form')
        viewer.page_tools_button = panel_button('페이지 정리', lambda: None, 'pages')
        page_menu = action_menu(viewer.page_tools_button)
        for text, callback, icon in (
            ('페이지 삭제', viewer.remove_pages, 'delete'),
            ('앞으로 이동', lambda: viewer.move_current_page(-1), 'up'),
            ('뒤로 이동', lambda: viewer.move_current_page(1), 'down'),
            ('페이지 정리 도구 보기', lambda: viewer.show_all_tools('pages'), 'pages'),
        ):
            page_menu.addAction(action_icon(icon, page_menu), tr(text)).triggered.connect(callback)
        viewer.move_up_button = page_menu.actions()[1]
        viewer.move_down_button = page_menu.actions()[2]
        viewer.page_tools_button.setMenu(page_menu)
        viewer.view_tools_button = panel_button('복사·보기', lambda: None, 'copy')
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
        for index, item in enumerate((viewer.panel_all_tools_button, viewer.form_button,
                                      viewer.page_tools_button, viewer.panel_scan_button,
                                      viewer.panel_security_button, viewer.panel_export_button,
                                      viewer.panel_optimize_button, viewer.view_tools_button,
                                      viewer.undo_button, viewer.redo_button,
                                      viewer.history_button), start=1):
            row.removeWidget(item)
            row.insertWidget(index, item)
        row.addStretch(1)
        viewer.editing_toggle.toggled.connect(panel.setVisible)
        viewer.editing_toggle.setAccessibleName(tr('도구 목록 표시'))
        apply_style(self, '''
            QWidget#workspaceHeader {background:#f7f9fc;}
            QPushButton {background:#f7f9fc; border:0; padding:7px 12px; border-radius:5px;}
            QPushButton:hover {background:#f1f5fb;}
            QPushButton:checked {background:#dbe6ff;}
        ''')
        apply_style(editing, '''
            QWidget#editingActions {background:white;}
            QLabel#toolsHeading {color:#263246; font-weight:600; padding:5px;}
            QPushButton {text-align:left; background:white; min-height:0; padding:6px 7px; border:0; border-radius:5px;}
            QPushButton:hover {background:#f1f5fb;}
        ''')
        apply_style(panel, 'QScrollArea#toolsPanel {background:white; border:0; border-radius:0;}')
        for key, callback in (('Ctrl+Z', viewer.undo_edit), ('Ctrl+Y', viewer.redo_edit),
                              ('Ctrl+Shift+Z', viewer.redo_edit), ('Ctrl+Shift+T', viewer.show_all_tools)):
            shortcut = QShortcut(QKeySequence(key), viewer)
            shortcut.activated.connect(callback)
        self.refresh_history()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for button, label in self._compact_buttons:
            button.setText(label)
        for button, label in self._compact_buttons:
            if self.layout().sizeHint().width() <= self.width():
                break
            button.setText('')

    def refresh_history(self):
        viewer = self.viewer
        history = getattr(viewer, 'edit_history', None)
        viewer.undo_button.setEnabled(bool(history and history.can_undo))
        viewer.redo_button.setEnabled(bool(history and history.can_redo))
        viewer.history_button.setEnabled(bool(history and (history.can_undo or history.can_redo or viewer.dirty)))
        viewer.undo_button.setToolTip(tr('실행 취소: {action} · Ctrl+Z', action=tr(history.undo_label))
                                      if history and history.can_undo else tr('실행 취소 · Ctrl+Z'))
        viewer.redo_button.setToolTip(tr('다시 실행: {action} · Ctrl+Y', action=tr(history.redo_label))
                                      if history and history.can_redo else tr('다시 실행 · Ctrl+Y'))
        if history:
            viewer.history_button.setText(tr('변경 내역 · {count}', count=history.position))


class NavigationStrip(QWidget):
    """Compact left-hand navigation for showing and hiding page thumbnails."""
    def __init__(self, viewer):
        super().__init__(viewer)
        self.setObjectName('navigationStrip')
        self.setFixedWidth(42)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 5, 3, 5)
        button = QPushButton(self)
        button.setFixedSize(36, 36)
        button.setCheckable(True)
        set_action_icon(button, 'thumbnail')
        button.setToolTip(tr('페이지 목록'))
        button.setAccessibleName(tr('페이지 목록'))
        button.toggled.connect(viewer.sidebar_toggle.setChecked)
        viewer.sidebar_toggle.toggled.connect(button.setChecked)
        viewer.sidebar_toggle.hide()
        viewer.thumbnail_rail_button = button
        layout.addWidget(button)
        layout.addStretch(1)
        apply_style(self, '''
            QWidget#navigationStrip {background:#f7f9fc;}
            QPushButton {background:#f7f9fc; border:0; border-radius:4px; padding:4px;}
            QPushButton:hover {background:#f1f5fb;}
            QPushButton:checked {background:#dbe6ff;}
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
