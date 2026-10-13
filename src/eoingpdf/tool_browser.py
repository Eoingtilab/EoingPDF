"""Searchable tool library with a compact, keyboard-friendly task selector."""
from PySide6.QtCore import Qt, Signal, QSize, QRect
from PySide6.QtGui import QFont, QShortcut, QKeySequence, QPalette
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QPushButton, QStyledItemDelegate,
    QStyleOptionViewItem, QStyle, QAbstractItemView)

from .localization import tr
from .sdk_theme import apply_style
from .tool_catalog import CATEGORIES, BY_KEY, find_tools


class ToolDelegate(QStyledItemDelegate):
    """Wrap descriptions to the actual viewport, including narrow/DPI layouts."""

    def sizeHint(self, option, index):
        panel = QStyleOptionViewItem(option)
        self.initStyleOption(panel, index)
        width = max(120, self.parent().viewport().width() - 28)
        font = QFont(panel.font)
        font.setBold(True)
        from PySide6.QtGui import QFontMetrics
        title = QFontMetrics(font).boundingRect(QRect(0, 0, width, 10000),
            Qt.TextWordWrap, index.data(Qt.UserRole + 1))
        description = QFontMetrics(panel.font).boundingRect(QRect(0, 0, width, 10000),
            Qt.TextWordWrap, index.data(Qt.UserRole + 2))
        return QSize(width + 28, max(68, title.height() + description.height() + 24))

    def paint(self, painter, option, index):
        panel = QStyleOptionViewItem(option)
        self.initStyleOption(panel, index)
        panel.text = ''
        style = panel.widget.style() if panel.widget else self.parent().style()
        style.drawControl(QStyle.CE_ItemViewItem, panel, painter, panel.widget)
        painter.save()
        # SDK selection backgrounds are a soft surface in both themes. Qt's
        # global HighlightedText is white for the primary blue and would make
        # selected rows unreadable on the light selected surface.
        painter.setPen(panel.palette.color(QPalette.Text))
        font = QFont(panel.font)
        font.setBold(True)
        painter.setFont(font)
        bounds = option.rect.adjusted(14, 10, -14, -10)
        title = painter.boundingRect(bounds, Qt.TextWordWrap, index.data(Qt.UserRole + 1))
        painter.drawText(title, Qt.TextWordWrap, index.data(Qt.UserRole + 1))
        painter.setFont(panel.font)
        description = QRect(bounds.left(), title.bottom() + 5, bounds.width(),
                            max(0, bounds.bottom() - title.bottom() - 5))
        painter.drawText(description, Qt.TextWordWrap, index.data(Qt.UserRole + 2))
        painter.restore()


class ToolBrowser(QDialog):
    tool_selected = Signal(str)

    def __init__(self, parent=None, allowed_keys=None, category='all'):
        super().__init__(parent)
        self.allowed_keys = set(allowed_keys) if allowed_keys is not None else None
        self.setWindowTitle(tr('어잉PDF · 전체 도구'))
        self.resize(720, 540)
        self.setMinimumSize(480, 380)
        apply_style(self, 'QDialog {background:#f7f9fc;} QLabel {color:#263246;}'
            'QLineEdit, QComboBox {background:white;color:#263246;border:1px solid #dae2f0;'
            'border-radius:6px;padding:8px;}'
            'QListWidget {background:white;color:#263246;border:1px solid #dae2f0;'
            'border-radius:8px;outline:0;}'
            'QListWidget::item {border-bottom:1px solid #e7ecf3;}'
            'QListWidget::item:selected {background:#dbe6ff;color:#183b8f;}'
            'QListWidget::item:hover:!selected {background:#f1f5fb;}'
            'QPushButton {padding:8px 14px;min-height:20px;}'
            'QPushButton#recommended {background:#edf2ff;color:#183b8f;'
            'border:1px solid #b9cbed;border-radius:6px;}'
            'QPushButton#recommended:hover {background:#dbe6ff;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        heading = QLabel(tr('필요한 작업을 찾아보세요'))
        heading_font = QFont(heading.font())
        heading_font.setPointSize(heading_font.pointSize() + 3)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        layout.addWidget(heading)
        featured = QHBoxLayout()
        self.featured_buttons = {}
        for key, title in (('presentation', tr('슬라이드쇼 · F5')),
                           ('stamp', tr('직인 및 서명 넣기'))):
            if self.allowed_keys is not None and key not in self.allowed_keys:
                continue
            button = QPushButton(title)
            button.setObjectName('recommended')
            button.setAutoDefault(False)
            button.setToolTip(tr(BY_KEY[key].description))
            button.clicked.connect(lambda checked=False, tool=key: self.choose(tool))
            featured.addWidget(button, 1)
            self.featured_buttons[key] = button
        if self.featured_buttons:
            layout.addLayout(featured)
        self.search = QLineEdit()
        self.search.setObjectName('toolSearch')
        self.search.setPlaceholderText(tr('도구 검색 · 예: 도장, 워터마크, 분할, OCR'))
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName(tr('도구 검색'))
        layout.addWidget(self.search)
        filters = QHBoxLayout()
        self.category = QComboBox()
        self.category.setObjectName('toolCategory')
        self.category.addItem(tr('전체 도구'), 'all')
        self.category.addItem(tr('추천 도구'), 'recommended')
        for group in CATEGORIES:
            self.category.addItem(tr(group.title), group.key)
        self.category.setAccessibleName(tr('작업 분류'))
        filters.addWidget(self.category, 1)
        self.count = QLabel()
        filters.addWidget(self.count)
        layout.addLayout(filters)
        self.results = QListWidget()
        self.results.setObjectName('toolResults')
        self.results.setWordWrap(True)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.results.setItemDelegate(ToolDelegate(self.results))
        self.results.setAccessibleName(tr('도구 목록'))
        layout.addWidget(self.results, 1)
        self.empty = QLabel(tr('검색 결과가 없습니다. 다른 검색어나 전체 도구를 선택해 주세요.'))
        self.empty.setWordWrap(True)
        self.empty.hide()
        layout.addWidget(self.empty)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.open_button = QPushButton(tr('선택한 도구 열기'))
        self.open_button.setObjectName('primary')
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(self.open_selected)
        buttons.addWidget(self.open_button)
        self.close_button = QPushButton(tr('닫기'))
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.search.textChanged.connect(self.refresh)
        self.category.currentIndexChanged.connect(self.refresh)
        self.results.itemDoubleClicked.connect(lambda _: self.open_selected())
        self.results.currentRowChanged.connect(lambda _: self.open_button.setEnabled(
            self.results.currentItem() is not None))
        self.search.returnPressed.connect(self.open_selected)
        QShortcut(QKeySequence('Ctrl+F'), self).activated.connect(self.focus_search)
        self.select_category(category)
        self.refresh()
        self.search.setFocus()

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def select_category(self, category):
        index = self.category.findData(category)
        self.category.setCurrentIndex(max(0, index))

    def refresh(self, *_):
        selected = self.results.currentItem()
        previous = selected.data(Qt.UserRole) if selected else None
        entries = find_tools(self.search.text(), self.category.currentData(), self.allowed_keys)
        self.results.clear()
        groups = {group.key: group for group in CATEGORIES}
        selected_row = 0
        for row, entry in enumerate(entries):
            title = tr(entry.title)
            description = tr('{category} · {description}',
                category=tr(groups[entry.category].title), description=tr(entry.description))
            item = QListWidgetItem(title + '\n' + description)
            item.setData(Qt.UserRole, entry.key)
            item.setData(Qt.UserRole + 1, title)
            item.setData(Qt.UserRole + 2, description)
            from .advanced import TOOLS
            item.setToolTip(tr(TOOLS[entry.key][1]) if entry.key in TOOLS else tr(entry.description))
            self.results.addItem(item)
            if entry.key == previous:
                selected_row = row
        if entries:
            self.results.setCurrentRow(selected_row)
        self.open_button.setEnabled(bool(entries))
        self.empty.setVisible(not entries)
        self.count.setText(tr('{count}개 도구', count=len(entries)))
        self.results.doItemsLayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'results'):
            self.results.doItemsLayout()

    def choose(self, key):
        if key in BY_KEY and (self.allowed_keys is None or key in self.allowed_keys):
            self.accept()
            self.tool_selected.emit(key)

    def open_selected(self):
        item = self.results.currentItem()
        if item:
            self.choose(item.data(Qt.UserRole))
