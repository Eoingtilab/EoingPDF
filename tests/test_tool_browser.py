"""Every PDF function remains discoverable by task, search and keyboard."""
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.advanced import TOOLS
from eoingpdf.tool_catalog import CATEGORIES, ENTRIES, BY_KEY, RECOMMENDED, find_tools
from eoingpdf.tool_browser import ToolBrowser
from eoingpdf.localization import install_language


def keys(dialog):
    return [dialog.results.item(row).data(Qt.UserRole)
            for row in range(dialog.results.count())]


@pytest.mark.parametrize('tool, preview', [('watermark_text', True), ('markdown', False)])
def test_enter_uses_primary_action_and_text_undo_stays_in_dialog(tmp_path, monkeypatch, tool, preview):
    import pymupdf as pdf
    from eoingpdf.viewer import PdfViewer
    from eoingpdf.advanced_ui import AdvancedDialog
    source = tmp_path / 'keyboard.pdf'
    with pdf.open() as document:
        document.new_page()
        document.new_page()
        document.save(source)
    calls = []
    monkeypatch.setattr(AdvancedDialog, 'start', lambda self, preview=False: calls.append(('start', preview)))
    monkeypatch.setattr(AdvancedDialog, 'choose_tool', lambda self: calls.append(('picker', None)))
    viewer = PdfViewer(source)
    viewer.move_current_page(1)
    dialog = AdvancedDialog(viewer)
    dialog.tool.setCurrentIndex(dialog.tool.findData(tool))
    try:
        dialog.show()
        field = dialog.watermark_text if preview else dialog.password
        field.setFocus()
        field.insert('Typing')
        QTest.keyClick(field, Qt.Key_Z, Qt.ControlModifier)
        assert not field.text()
        assert viewer.pages == [1, 0] and viewer.edit_history.position == 1
        QTest.keyClick(field, Qt.Key_Return)
        assert calls == [('start', preview)]
    finally:
        dialog.reject()
        viewer.reset_edits()
        viewer.close()


def test_catalog_covers_all_transforms_once_and_valid_categories():
    values = [entry.key for entry in ENTRIES]
    assert len(values) == len(set(values))
    assert set(values).intersection(TOOLS) == set(TOOLS)
    assert set(values) - set(TOOLS) == {'presentation', 'form', 'table', 'copy_image', 'viewmode'}
    assert all(entry.category in {group.key for group in CATEGORIES} for entry in ENTRIES)
    assert all(key in BY_KEY for key in RECOMMENDED)


@pytest.mark.parametrize('query, expected', [
    ('도장', {'stamp'}), ('watermark', {'watermark_text', 'watermark_png'}),
    ('워터마크', {'watermark_text', 'watermark_png'}),
    ('표 서식', {'auto_forms', 'form'}), ('OCR', {'searchable', 'ocr_redact', 'safe_submission'}),
    ('분할', {'split_ranges', 'split_groups', 'split_toc', 'split_spread', 'slice_a4'}),
    ('ＣＡＤ', {'dxf'}), ('PAGE impossibleterm', set()),
])
def test_search_uses_korean_task_aliases_and_normalizes(query, expected):
    found = {entry.key for entry in find_tools(query)}
    assert found == expected


def test_full_category_title_search_is_distinct_from_feature_keywords():
    for category in CATEGORIES:
        assert {entry.key for entry in find_tools(category.title)} == {
            entry.key for entry in ENTRIES if entry.category == category.key}


def test_browser_filters_tools_and_opens_selected_item_with_keyboard():
    dialog = ToolBrowser()
    chosen = []
    dialog.tool_selected.connect(chosen.append)
    dialog.show()
    try:
        assert set(keys(dialog)) == set(BY_KEY)
        dialog.select_category('pages')
        assert set(keys(dialog)) == {entry.key for entry in ENTRIES if entry.category == 'pages'}
        dialog.select_category('all')
        dialog.search.setText('도장')
        assert keys(dialog) == ['stamp']
        QTest.keyClick(dialog.search, Qt.Key_Return)
        assert chosen == ['stamp']
        assert dialog.result() == QDialog.Accepted and not dialog.isVisible()
    finally:
        dialog.close()


def test_browser_empty_search_cannot_launch_and_escape_cancels():
    dialog = ToolBrowser()
    chosen = []
    dialog.tool_selected.connect(chosen.append)
    dialog.show()
    try:
        dialog.search.setText('없는 기능 impossibletool')
        assert not keys(dialog) and not dialog.open_button.isEnabled()
        assert dialog.empty.isVisible()
        dialog.open_selected()
        assert not chosen and dialog.isVisible()
        QTest.keyClick(dialog.search, Qt.Key_Escape)
        assert dialog.result() == QDialog.Rejected and not dialog.isVisible()
    finally:
        dialog.close()


def test_recommended_and_allowed_keys_share_the_same_catalog():
    dialog = ToolBrowser(allowed_keys=TOOLS, category='recommended')
    chosen = []
    dialog.tool_selected.connect(chosen.append)
    try:
        assert keys(dialog) == [key for key in RECOMMENDED if key in TOOLS]
        assert set(dialog.featured_buttons) == {'stamp'}
        dialog.select_category('all')
        assert set(keys(dialog)) == set(TOOLS)
        dialog.choose('presentation')
        assert not chosen
        dialog.featured_buttons['stamp'].click()
        assert chosen == ['stamp']
    finally:
        dialog.close()


@pytest.mark.parametrize('locale', ('ko-KR', 'en-US', 'ja-JP'))
def test_small_tool_browser_contains_controls_and_wraps_rows(locale):
    app = QApplication.instance()
    previous = getattr(app, 'eoing_locale', 'ko-KR')
    install_language(app, locale)
    dialog = ToolBrowser()
    dialog.resize(480, 380)
    dialog.show()
    QTest.qWait(25)
    try:
        for widget in (dialog.search, dialog.category, dialog.results,
                       dialog.open_button, dialog.close_button,
                       *dialog.featured_buttons.values()):
            rect = widget.geometry()
            assert rect.left() >= 0 and rect.top() >= 0
            assert rect.right() < dialog.width() and rect.bottom() < dialog.height()
        assert dialog.results.verticalScrollBar().maximum() > 0
        # Long descriptions are measured at the live viewport width rather than
        # clipped to a fixed row height when accessibility fonts grow.
        before = max(dialog.results.visualItemRect(dialog.results.item(row)).height()
                     for row in range(dialog.results.count()))
        dialog.results.setFont(QFont(dialog.results.font().family(), 13))
        app.processEvents()
        dialog.results.doItemsLayout()
        heights = [dialog.results.visualItemRect(dialog.results.item(row)).height()
                   for row in range(dialog.results.count())]
        assert max(heights) > before
        assert dialog.results.horizontalScrollBar().maximum() == 0
    finally:
        dialog.close()
        install_language(app, previous)
