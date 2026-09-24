import sys
import time
from pathlib import Path
import pymupdf as pdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.search_ui import SearchDialog


def wait_idle(dialog):
    deadline = time.monotonic() + 20
    while dialog.worker is not None and time.monotonic() < deadline:
        QTest.qWait(20)
    assert dialog.worker is None, 'Search child did not exit'


def test_folder_button_search_enter_and_open_real_result(tmp_path, monkeypatch):
    model = ROOT / 'assets/search'
    if not (model / 'model.onnx').exists():
        pytest.skip('Prepare the real evaluation ONNX model first')
    folder = tmp_path / 'documents'; folder.mkdir()
    source = folder / 'account.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((72, 72), 'Reset your password using email verification.')
        doc.save(source)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(folder))
    dialog = SearchDialog(cache_folder=tmp_path / 'cache')
    assert dialog.model_folder == model
    dialog.show()
    try:
        dialog.choose_button.click()
        assert dialog.worker is not None and not dialog.search_button.isEnabled()
        wait_idle(dialog)
        assert dialog.indexed_folder == str(folder.resolve())
        dialog.query.setText('Forgot account credentials')
        QTest.keyClick(dialog.query, Qt.Key_Return)
        wait_idle(dialog)
        assert dialog.results.count() == 1
        dialog.open_button.click()
        QTest.qWait(40)
        assert dialog.viewer is not None and dialog.viewer.isVisible()
        assert dialog.viewer.path == source
        assert dialog.viewer.canvas.search_highlight is not None
        dialog.viewer.close()
        dialog.refresh_button.click()
        dialog.close()
        assert dialog.pending_close
        wait_idle(dialog)
        assert not dialog.isVisible()
        dialog.show()
        assert not dialog.pending_close
        original = source.read_bytes()
        database = dialog.database()
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.No)
        dialog.delete_button.click()
        assert database.exists()
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
        dialog.delete_button.click()
        assert not database.exists() and source.read_bytes() == original
        assert dialog.indexed_folder is None and dialog.results.count() == 0
        assert not dialog.search_button.isEnabled() and not dialog.delete_button.isEnabled()
        assert dialog.refresh_button.isEnabled()
    finally:
        if dialog.worker:
            dialog.cancel()
            wait_idle(dialog)
        dialog.close()


def test_missing_model_surfaces_error_and_reenables_folder_selection(tmp_path, monkeypatch):
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    dialog = SearchDialog(model_folder=tmp_path / 'missing', cache_folder=tmp_path / 'cache')
    dialog.folder.setText(str(tmp_path))
    dialog.show()
    try:
        dialog.build()
        wait_idle(dialog)
        assert dialog.choose_button.isEnabled()
        assert dialog.indexed_folder is None
        assert dialog.results.count() == 0
        assert dialog.status.text()
    finally:
        dialog.close()


@pytest.mark.parametrize('locale, button, marker', [('ko-KR', '검색', '3페이지'),
    ('en-US', 'Search', 'Page 3'), ('ja-JP', '検索', '3ページ')])
def test_search_localization_preserves_document_content(tmp_path, locale, button, marker):
    import json
    from PySide6.QtWidgets import QApplication
    from eoingpdf.localization import install_language
    app = QApplication.instance()
    previous = getattr(app, 'eoing_locale', 'ko-KR')
    install_language(app, locale)
    dialog = SearchDialog(cache_folder=tmp_path)
    try:
        assert dialog.search_button.text() == button
        dialog.completed('search', True, json.dumps([dict(path='example.pdf', page=2,
            text='원문 {변수} <document> 日本語')]))
        assert dialog.results.count() == 1
        assert marker in dialog.results.item(0).text()
        assert '원문 {변수} <document> 日本語' in dialog.results.item(0).text()
    finally:
        dialog.close()
        install_language(app, previous)
