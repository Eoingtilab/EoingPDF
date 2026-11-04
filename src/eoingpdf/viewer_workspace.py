"""Task-focused reader chrome; editing history belongs to the viewer draft."""
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                              QPushButton, QLabel, QMenu, QListWidget, QScrollArea,
                              QFrame, QMenuBar)
from .action_icons import action_icon, set_action_icon
from .flow_layout import FlowLayout
from .localization import tr
from .sdk_theme import apply_style


def action_menu(parent):
    menu = QMenu(parent)
    apply_style(menu, 'QMenu::item:selected {background:#416ae6;color:white;}')
    return menu


class QuickActionLayout(FlowLayout):
    """Keep file actions at the right when the full row fits; wrap when narrow."""
    def arrange(self, rect, test):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        sizes = [item.sizeHint() for item in self.items]
        total = sum(size.width() for size in sizes) + self.spacing() * max(0, len(sizes) - 1)
        if total > area.width():
            return super().arrange(rect, test)
        from PySide6.QtCore import QRect
        x = area.x()
        for index, (item, size) in enumerate(zip(self.items, sizes)):
            if index == len(sizes) - 2:
                x += area.width() - total
            if not test:
                item.setGeometry(QRect(x, area.y(), size.width(), size.height()))
            x += size.width() + self.spacing()
        return max((size.height() for size in sizes), default=0) + margins.top() + margins.bottom()


class WorkspaceHeader(QWidget):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.setObjectName('workspaceHeader')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        menu_bar = QMenuBar(self)
        menu_bar.setObjectName('readerMenuBar')
        for title, entries in (
            ('파일', (('PDF 열기', viewer.choose_pdf), ('사본 저장', viewer.save_changes), ('닫기', viewer.close))),
            ('편집', (('실행 취소', viewer.undo_edit), ('다시 실행', viewer.redo_edit),
                    ('변경 내역', lambda: HistoryDialog(viewer).exec()))),
            ('보기', (('페이지 목록', lambda: viewer.sidebar_toggle.toggle()),
                    ('편집 도구', lambda: viewer.editing_toggle.toggle()),
                    ('모든 도구', viewer.show_all_tools))),
            ('창', (('슬라이드쇼 · F5', viewer.start_slideshow),)),
            ('도움말', (('설정·도움말', lambda: viewer.settings_button.showMenu()),)),
        ):
            menu = menu_bar.addMenu(tr(title))
            for label, callback in entries:
                menu.addAction(tr(label)).triggered.connect(callback)
        layout.addWidget(menu_bar)
        tabs = QWidget(self)
        tabs.setObjectName('readerTabs')
        tab_row = QHBoxLayout(tabs)
        tab_row.setContentsMargins(8, 0, 8, 0)
        tab_row.setSpacing(0)
        home = QPushButton(tr('홈'), tabs)
        viewer.home_button = home
        home.setObjectName('readerTabButton')
        set_action_icon(home, 'open')
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
        home.clicked.connect(show_home)
        tab_row.addWidget(home)
        tools_tab = QPushButton(tr('도구'), tabs)
        viewer.tools_tab_button = tools_tab
        tools_tab.setObjectName('readerTabButton')
        set_action_icon(tools_tab, 'tools')
        tools_tab.clicked.connect(viewer.show_all_tools)
        tab_row.addWidget(tools_tab)
        document_tab = QLabel(viewer.windowTitle(), tabs)
        document_tab.setObjectName('documentTab')
        document_tab.setMinimumWidth(160)
        document_tab.setMaximumWidth(360)
        viewer.windowTitleChanged.connect(document_tab.setText)
        tab_row.addWidget(document_tab)
        tab_row.addStretch(1)
        layout.addWidget(tabs)
        quick = QWidget(self)
        quick.setObjectName('quickActions')
        row = QuickActionLayout(quick)
        row.setContentsMargins(0, 0, 0, 0)

        def button(text, callback, icon, name=''):
            result = QPushButton(tr(text))
            result.setAutoDefault(False)
            result.setObjectName(name)
            set_action_icon(result, icon)
            result.clicked.connect(callback)
            row.addWidget(result)
            return result

        viewer.open_button = button('PDF 열기', viewer.choose_pdf, 'open')
        viewer.slideshow_button = button('슬라이드쇼 · F5', viewer.start_slideshow,
                                         'play', 'slideshowAction')
        viewer.slideshow_button.setToolTip(tr('현재 페이지부터 전체 화면으로 발표합니다.'))
        viewer.stamp_button = button('직인·서명 넣기', viewer.insert_stamp, 'stamp', 'insertStamp')
        viewer.stamp_button.setToolTip(tr('JPG·PNG의 흰 배경을 제거하고 위치와 크기를 직접 조절합니다.'))
        viewer.more_features_button = button('모든 도구', viewer.show_all_tools,
                                             'tools', 'allTools')
        viewer.more_features_button.setToolTip(tr('작업별로 찾거나 이름으로 도구를 검색합니다.'))
        viewer.more_features_menu = action_menu(viewer.more_features_button)
        viewer.sidebar_toggle = button('페이지 목록', lambda: None, 'thumbnail', 'sidebarToggle')
        viewer.sidebar_toggle.setCheckable(True)
        viewer.sidebar_toggle.setChecked(False)
        viewer.sidebar_toggle.toggled.connect(lambda visible: viewer.thumbnails.setVisible(visible))
        viewer.editing_toggle = button('편집 도구', lambda: None, 'pages', 'editingToggle')
        viewer.editing_toggle.setCheckable(True)
        viewer.editing_toggle.setChecked(True)
        viewer.save_button = button('사본 저장', viewer.save_changes,
                                    'save', 'saveCopyAction')
        viewer.save_button.setToolTip(tr('현재 화면의 변경을 새 PDF로 저장합니다. · Ctrl+S'))
        viewer.save_button.setEnabled(False)
        viewer.close_button = button('닫기', viewer.close, 'close')
        layout.addWidget(quick)

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
        viewer.panel_all_tools_button = button('도구 검색', viewer.show_all_tools, 'search')
        viewer.panel_scan_button = button('스캔·문자 인식', lambda: viewer.show_all_tools('scan'), 'scan')
        viewer.panel_security_button = button('보안·개인정보', lambda: viewer.show_all_tools('security'), 'security')
        viewer.panel_export_button = button('복사·내보내기', lambda: viewer.show_all_tools('export'), 'export')
        viewer.panel_optimize_button = button('압축·복구', lambda: viewer.show_all_tools('optimize'), 'optimize')
        viewer.undo_button = button('실행 취소', viewer.undo_edit, 'undo')
        viewer.redo_button = button('다시 실행', viewer.redo_edit, 'redo')
        viewer.history_button = button('변경 내역', lambda: HistoryDialog(viewer).exec(), 'history')
        viewer.form_button = button('양식 입력', viewer.edit_form, 'form')
        viewer.page_tools_button = button('페이지 정리', lambda: None, 'pages')
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
        viewer.view_tools_button = button('복사·보기', lambda: None, 'copy')
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
        viewer.editing_toggle.setAccessibleName(tr('편집 도구'))
        apply_style(self, '''
            QWidget#workspaceHeader {background:#f7f9fc;}
            QWidget#readerTabs {background:#f7f9fc; border-bottom:1px solid #dae2f0;}
            QLabel#documentTab {background:#ffffff; color:#263246; padding:7px 16px; border:1px solid #d0d0d0; border-bottom:0;}
            QPushButton#readerTabButton {background:#f7f9fc; border-radius:0; padding:7px 12px;}
            QPushButton#readerTabButton:hover {background:#dbe6ff;}
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
