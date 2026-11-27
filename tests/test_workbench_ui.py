"""End-to-end UI tests for Stirling-style workbench flows, Save As, Multi-Tool, and Pipelines."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import pymupdf as pdf
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPlainTextEdit

from eoingpdf.diff_ui import DiffDialog
from eoingpdf.viewer import PdfViewer
from eoingpdf.workbench_dialogs import EXPORT_FORMATS, PdfInfoDialog, SaveAsDialog, SignDrawDialog


def _wait_until(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(25)
    assert predicate()


def _make_pdf(path: Path, texts: list[str]) -> bytes:
    with pdf.open() as doc:
        for text in texts:
            doc.new_page(width=595, height=842).insert_text((60, 80), text)
        doc.save(path)
    return path.read_bytes()


def test_empty_home_and_library_switching(tmp_path, monkeypatch):
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    doc_a = tmp_path / 'alpha.pdf'
    doc_b = tmp_path / 'beta.pdf'
    note = tmp_path / 'notes.txt'
    _make_pdf(doc_a, ['Alpha page'])
    _make_pdf(doc_b, ['Beta 1', 'Beta 2'])
    note.write_text('sample', encoding='utf-8')

    viewer = PdfViewer()
    viewer.show()
    try:
        assert viewer.path is None
        assert viewer.center_stack.currentIndex() == 2
        assert viewer.library_panel.list.count() == 0
        assert not viewer.save_as_button.isEnabled()

        viewer.add_to_library([doc_a, note])
        QApplication.processEvents()
        assert viewer.library_panel.list.count() == 2
        assert viewer.path == doc_a
        assert viewer.count == 1
        assert viewer.center_stack.currentIndex() == 0
        assert viewer.save_as_button.isEnabled()

        viewer.add_to_library([doc_b])
        assert viewer.library_panel.list.count() == 3
        viewer.library_panel.open_requested.emit(str(doc_b))
        QApplication.processEvents()
        assert viewer.path == doc_b
        assert viewer.count == 2
    finally:
        viewer.dirty = False
        viewer.close()
        viewer.deleteLater()


def test_save_as_dialog_exports_pdf_html_png_json(tmp_path, monkeypatch):
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *a, **kw: QMessageBox.Discard)
    monkeypatch.setattr('eoingpdf.workbench_dialogs.QMessageBox.question', lambda *a, **kw: QMessageBox.Yes)
    source = tmp_path / 'report.pdf'
    original_bytes = _make_pdf(source, ['Hello Export World', 'Second Slide'])

    viewer = PdfViewer(source)
    dialog = SaveAsDialog(viewer)
    try:
        assert dialog.format_combo.count() == len(EXPORT_FORMATS)
        for fmt_key, filename in (
            ('html', 'out.html'),
            ('json', 'out.json'),
            ('png', 'page1.png'),
            ('pdf', 'copy.pdf'),
        ):
            idx = dialog.format_combo.findData(fmt_key)
            assert idx >= 0
            dialog.format_combo.setCurrentIndex(idx)
            target = tmp_path / filename
            dialog.target_edit.setText(str(target))
            dialog.saved_path = None
            dialog.start_export()
            _wait_until(lambda: dialog.saved_path is not None and not dialog.worker.isRunning())
            assert target.is_file()

        assert 'Hello Export World' in (tmp_path / 'out.html').read_text(encoding='utf-8')
        data = json.loads((tmp_path / 'out.json').read_text(encoding='utf-8'))
        assert data['page_count'] == 2
        assert (tmp_path / 'page1.png').read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
        with pdf.open(tmp_path / 'copy.pdf') as exported_pdf:
            assert exported_pdf.page_count == 2
        assert hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256(original_bytes).hexdigest()
    finally:
        dialog.reject()
        dialog.deleteLater()
        viewer.dirty = False
        viewer.close()
        viewer.deleteLater()


def test_multi_tool_edit_rotate_blank_and_undo(tmp_path, monkeypatch):
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *a, **kw: QMessageBox.Discard)
    source = tmp_path / 'pages.pdf'
    original_bytes = _make_pdf(source, ['One', 'Two'])

    viewer = PdfViewer(source)
    try:
        viewer.toggle_multi_tool(True)
        assert viewer.center_stack.currentIndex() == 1
        assert len(viewer.multi_tool.entries) == 2

        viewer.multi_tool.grid.item(0).setSelected(True)
        viewer.multi_tool.rotate_selected(90)
        assert viewer.multi_tool.entries[0]['rotate'] == 90

        viewer.multi_tool.insert_blank_after()
        assert len(viewer.multi_tool.entries) == 3

        viewer.multi_tool.commit_to_viewer()
        assert viewer.center_stack.currentIndex() == 0
        assert viewer.count == 3
        assert viewer.dirty

        assert viewer.undo_edit()
        assert viewer.count == 2
        assert viewer.redo_edit()
        assert viewer.count == 3
        assert source.read_bytes() == original_bytes
    finally:
        viewer.multi_tool.entries.clear()
        viewer.dirty = False
        viewer.close()
        viewer.deleteLater()


def test_right_tools_dock_search_inline_runner_and_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *a, **kw: QMessageBox.Discard)
    source = tmp_path / 'inline.pdf'
    _make_pdf(source, ['Inline Runner Doc'])

    viewer = PdfViewer(source)
    try:
        dock = viewer.workspace_header.editing_panel
        dock.search_input.setText('QR')
        keys = [dock.tool_list.item(i).data(Qt.UserRole) for i in range(dock.tool_list.count())]
        assert 'qr_stamp' in keys

        dock.activate_tool('page_numbers')
        assert dock.tool_stack.currentIndex() == 1
        assert dock.inline_runner.current_key == 'page_numbers'

        dock.inline_runner._run(preview=True)
        _wait_until(lambda: dock.inline_runner.worker is None or not dock.inline_runner.worker.isRunning())
        _wait_until(lambda: dock.inline_runner.apply_btn.isEnabled())
        assert viewer.dirty
        assert viewer.edit_history.can_undo

        dock.activate_tool('pipeline')
        assert dock.tabs.currentIndex() == 1
        assert dock.pipeline_panel.steps_list.count() >= 1
    finally:
        viewer.dirty = False
        viewer.close()
        viewer.deleteLater()


def test_sign_draw_dialog_and_pdf_info_and_text_diff(tmp_path, monkeypatch):
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    before = tmp_path / 'before.pdf'
    after = tmp_path / 'after.pdf'
    _make_pdf(before, ['Clause A original'])
    _make_pdf(after, ['Clause A revised'])

    for style_idx in range(4):
        typed = SignDrawDialog()
        try:
            typed.tabs.setCurrentIndex(1)
            typed.name_edit.setText('홍길동')
            typed.style_combo.setCurrentIndex(style_idx)
            typed.accept_signature()
            assert typed.result() == QDialog.Accepted
            assert typed.result_png_path and typed.result_png_path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
        finally:
            typed.close()
            typed.deleteLater()

    drawn = SignDrawDialog()
    try:
        drawn.pad.strokes.append(([QPointF(20, 20), QPointF(120, 80)], QColor('#111827'), 4))
        drawn.accept_signature()
        assert drawn.result() == QDialog.Accepted
        assert drawn.result_png_path and drawn.result_png_path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
    finally:
        drawn.close()
        drawn.deleteLater()

    info = PdfInfoDialog(before)
    try:
        view = info.findChild(QPlainTextEdit)
        assert view is not None
        assert 'before.pdf' in view.toPlainText()
        assert '1' in view.toPlainText()
    finally:
        info.close()
        info.deleteLater()

    diff = DiffDialog(before=before, after=after)
    try:
        diff.mode.setCurrentIndex(3)
        _wait_until(lambda: diff.view_stack.currentIndex() == 1 and diff.text_diff.toPlainText() != '')
        txt = diff.text_diff.toPlainText()
        assert '-Clause A original' in txt
        assert '+Clause A revised' in txt
    finally:
        diff.close()
        diff.deleteLater()


def test_show_update_status_live_dialog(monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel, QPushButton, QWidget
    from eoingpdf.updates import show_update_status

    monkeypatch.setattr('eoingpdf.package_context.store_managed_updates', lambda: False)
    monkeypatch.setattr('eoingpdf.updates.update_info', lambda _cur: {'version': '2.9.9', 'sha256': 'a' * 64, 'url': 'https://example.invalid', 'kind': 'installer'})
    seen = {}

    def close_after_refresh():
        modal = QApplication.activeModalWidget()
        if modal is not None:
            texts = [lbl.text() for lbl in modal.findChildren(QLabel)]
            if any('2.9.9' in t for t in texts):
                seen['texts'] = texts
                seen['buttons'] = [b.text() for b in modal.findChildren(QPushButton)]
                modal.accept()
                return
        QTimer.singleShot(50, close_after_refresh)

    host = QWidget()
    QTimer.singleShot(80, close_after_refresh)
    try:
        show_update_status(host)
        assert seen.get('texts')
        assert any('2.9.9' in t for t in seen['texts'])
    finally:
        host.close()
        host.deleteLater()
