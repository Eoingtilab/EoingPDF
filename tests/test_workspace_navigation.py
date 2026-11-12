import sys
from pathlib import Path

import pymupdf as pdf
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QPushButton

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.viewer import PdfViewer
from eoingpdf.localization import tr


def test_workspace_categories_open_the_matching_tool_groups(tmp_path, monkeypatch):
    path = Path(tmp_path) / 'document.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(path)
    calls = []
    monkeypatch.setattr(PdfViewer, 'show_all_tools', lambda self, category='all': calls.append(category))
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    viewer = PdfViewer(path)
    viewer.show()
    QApplication.processEvents()
    try:
        for button in (viewer.panel_scan_button, viewer.panel_security_button,
                       viewer.panel_export_button, viewer.panel_optimize_button):
            viewer.workspace_header.editing_panel.ensureWidgetVisible(button)
            button.click()
        assert calls == ['scan', 'security', 'export', 'optimize']
        assert not viewer.dirty
    finally:
        viewer.close()


def test_workspace_panels_and_navigation_keep_current_document(tmp_path, monkeypatch):
    path = Path(tmp_path) / 'document.pdf'
    with pdf.open() as document:
        document.new_page()
        document.new_page()
        document.save(path)
    original = path.read_bytes()
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    viewer = PdfViewer(path)
    viewer.show()
    QApplication.processEvents()
    try:
        viewer.page.setValue(2)
        assert viewer.thumbnails.isVisible()
        viewer.editing_toggle.click()
        assert not viewer.workspace_header.editing_panel.isVisible()
        viewer.thumbnail_rail_button.click()
        assert not viewer.thumbnails.isVisible()
        viewer.editing_toggle.click()
        assert viewer.workspace_header.editing_panel.isVisible()
        assert viewer.page.value() == 2
        viewer.thumbnail_rail_button.click()
        assert viewer.thumbnails.isVisible()
        viewer.close_thumbnails_button.click()
        assert not viewer.thumbnails.isVisible()
        viewer.toggle_sidebar_mode()
        assert viewer.thumbnails.isVisible() and viewer.sidebar_toggle.isChecked()
        assert path.read_bytes() == original and not viewer.dirty
    finally:
        viewer.close()


def test_home_respects_unsaved_changes(tmp_path, monkeypatch):
    path = Path(tmp_path) / 'document.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(path)
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    viewer = PdfViewer(path)
    viewer.show()
    QApplication.processEvents()
    monkeypatch.setattr(viewer, 'confirm_leave', lambda: False)
    viewer.home_button.click()
    assert viewer.isVisible()
    monkeypatch.setattr(viewer, 'confirm_leave', lambda: True)
    viewer.close()


def test_header_is_one_row_and_tools_are_not_duplicated(tmp_path, monkeypatch):
    path = Path(tmp_path) / 'document.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(path)
    calls = []
    monkeypatch.setattr(PdfViewer, 'show_all_tools', lambda self, category='all': calls.append(category))
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    viewer = PdfViewer(path)
    try:
        for width in (960, 680):
            viewer.resize(width, 600)
            viewer.show()
            QApplication.processEvents()
            controls = (viewer.home_button, viewer.workspace_header.menu_bar,
                        viewer.slideshow_button, viewer.stamp_button,
                        viewer.save_button, viewer.close_button)
            centers = [item.mapTo(viewer, item.rect().center()) for item in controls]
            assert max(point.y() for point in centers) - min(point.y() for point in centers) <= 2
            assert all(left.x() < right.x() for left, right in zip(centers, centers[1:]))
            assert all(viewer.rect().contains(item.mapTo(viewer, QPoint(item.width() - 1, item.height() - 1)))
                       for item in controls)
        assert not viewer.workspace_header.findChildren(QPushButton, 'allTools')
        assert [menu.title() for menu in viewer.workspace_header._menus] == [tr(x) for x in ('파일', '편집', '보기', '창')]
        viewer.panel_all_tools_button.click()
        assert len(calls) == 1
        view_menu = viewer.workspace_header._menus[2]
        viewer.close_tools_button.click()
        assert not viewer.workspace_header.editing_panel.isVisible()
        view_menu.actions()[1].trigger()
        assert viewer.workspace_header.editing_panel.isVisible()
    finally:
        viewer.close()
