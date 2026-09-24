import sys
from pathlib import Path

import pymupdf as pdf
import pytest
from PySide6.QtWidgets import QPushButton, QFileDialog, QInputDialog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.viewer import PdfViewer


@pytest.mark.parametrize('encrypted', [False, True])
def test_recommended_name_saves_selected_pages_preserving_original(tmp_path, monkeypatch, encrypted):
    source = tmp_path / 'original.pdf'
    password = 'test-secret' if encrypted else ''
    with pdf.open() as doc:
        for text in ('First page', 'Second page'):
            doc.new_page().insert_text((72, 72), text)
        options = dict(encryption=pdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw='owner') if encrypted else {}
        doc.save(source, **options)
    original = source.read_bytes()
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args: (password, True))
    window = PdfViewer(source)
    try:
        window.pages = [1]
        window.dirty = True
        target = tmp_path / 'Recommended title.pdf'
        # Existing unrelated files must survive even when the file dialog accepts them.
        target.write_bytes(b'existing')
        selections = []
        def choose(parent, title, suggested, filters):
            selections.append(Path(suggested))
            return str(target), filters
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', choose)
        window.chips.display({'suggested_name': target.name, 'diagnostics': [
            {'action': 'rename', 'title': '제목으로 파일명 추천', 'code': 'D-09'}]})
        window.chips.findChild(QPushButton).click()
        assert selections == [target]
        assert source.read_bytes() == original
        assert target.read_bytes() == b'existing'
        assert window.path == tmp_path / 'Recommended title (1).pdf'
        assert not window.dirty
        with pdf.open(window.path) as saved:
            assert bool(saved.needs_pass) == encrypted
            if encrypted:
                assert saved.authenticate(password)
            assert len(saved) == 1
            assert 'Second page' in saved[0].get_text()
    finally:
        window.dirty = False
        window.close()


def test_recommendation_cancel_and_invalid_name_leave_document_untouched(tmp_path, monkeypatch):
    source = tmp_path / 'original.pdf'
    with pdf.open() as doc:
        doc.new_page()
        doc.save(source)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    window = PdfViewer(source)
    calls = []
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (calls.append(args) or '', ''))
    try:
        window.chips.suggested_name = '../outside.pdf'
        window.diagnostic_action('rename')
        assert not calls
        window.chips.suggested_name = 'Suggested.pdf'
        window.diagnostic_action('rename')
        assert len(calls) == 1
        assert window.path == source and not window.dirty
        assert list(tmp_path.iterdir()) == [source]
    finally:
        window.close()
