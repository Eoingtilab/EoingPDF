import sys
from pathlib import Path

import pymupdf as pdf
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.viewer import PdfViewer


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
        viewer.editing_toggle.click()
        assert not viewer.workspace_header.editing_panel.isVisible()
        viewer.sidebar_toggle.click()
        assert viewer.thumbnails.isVisible()
        viewer.editing_toggle.click()
        assert viewer.workspace_header.editing_panel.isVisible()
        assert viewer.page.value() == 2
        viewer.sidebar_toggle.click()
        assert not viewer.thumbnails.isVisible()
        viewer.toggle_sidebar_mode()
        assert viewer.thumbnails.isVisible() and viewer.sidebar_toggle.isChecked()
        assert path.read_bytes() == original and not viewer.dirty
    finally:
        viewer.close()
