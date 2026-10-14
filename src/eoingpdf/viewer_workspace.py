"""Task-focused reader chrome; editing history belongs to the viewer draft."""
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                              QPushButton, QLabel, QMenu, QListWidget)
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
        layout.setSpacing(4)
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
        viewer.save_button = button('사본 저장', viewer.save_changes,
                                    'save', 'saveCopyAction')
        viewer.save_button.setToolTip(tr('현재 화면의 변경을 새 PDF로 저장합니다. · Ctrl+S'))
        viewer.save_button.setEnabled(False)
        viewer.close_button = button('닫기', viewer.close, 'close')
        layout.addWidget(quick)

        editing = QWidget(self)
        editing.setObjectName('editingActions')
        row = FlowLayout(editing)
        row.setContentsMargins(0, 0, 0, 0)
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
        layout.addWidget(editing)
        apply_style(self, '''
            QWidget#workspaceHeader {background:#f7f9fc;}
            QPushButton {padding:7px 12px;border-radius:6px;}
        ''')
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
