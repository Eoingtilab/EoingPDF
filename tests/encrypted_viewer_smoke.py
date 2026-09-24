"""Encrypted viewer opens without decrypted disk copies; save preserves encryption."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from unittest.mock import patch
import pymupdf as pdf
from PySide6.QtWidgets import QApplication, QMessageBox
from eoingpdf.viewer import PdfViewer, SlideShow

app = QApplication.instance() or QApplication([])
root = Path('temp/encrypted-viewer-test')
root.mkdir(parents=True, exist_ok=True)
source = root / 'locked.pdf'
target = root / 'saved.pdf'
# Fixture output belongs exclusively to this smoke test.
if target.exists():
    target.unlink()
with pdf.open() as doc:
    for i in range(3):
        doc.new_page().insert_text((60, 60), f'Encrypted page {i + 1}')
    doc.save(source, encryption=pdf.PDF_ENCRYPT_AES_256,
             user_pw='test-viewer', owner_pw='test-owner')
before = source.read_bytes()
with patch('eoingpdf.viewer.QInputDialog.getText', side_effect=[('wrong', True), ('test-viewer', True)]) as prompt, \
     patch('eoingpdf.viewer.QMessageBox.warning') as warning, \
     patch('eoingpdf.license_ui.ensure_license', return_value=True), \
     patch('eoingpdf.sniffer_ui.MicroSniffer.start'):
    viewer = PdfViewer(source)
    assert prompt.call_count == 2 and warning.call_count == 1
    viewer.show()
    app.processEvents()
    viewer.fill_thumbnails()
    assert not viewer.canvas.pixmap().isNull()
    assert viewer.thumbnail_cache
    viewer.page.setValue(2)
    assert viewer.page.value() == 2
    slides = SlideShow(source, parent=viewer, password=viewer.password)
    slides.render()
    assert not slides.canvas.pixmap().isNull()
    slides.show_presenter()
    app.processEvents()
    slides.reject()
    with patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.Yes):
        viewer.stage_delete({1})
    assert viewer.pages == [0, 2]
    with patch('eoingpdf.viewer.QFileDialog.getSaveFileName', return_value=(str(target), 'PDF')):
        assert viewer.save_changes()
    with pdf.open(target) as check:
        assert check.needs_pass and not check.authenticate('wrong')
        assert check.authenticate('test-viewer')
        assert len(check) == 2 and 'page 3' in check[1].get_text()
    assert source.read_bytes() == before
    old_path, old_pages = viewer.path, list(viewer.pages)
    with patch('eoingpdf.viewer.QInputDialog.getText', return_value=('', False)):
        try:
            viewer.load(source)
        except ValueError as error:
            assert '취소' in str(error)
        else:
            raise AssertionError('Cancelled password must not replace the document')
    assert viewer.path == old_path and viewer.pages == old_pages
    viewer.close()
print('PASS: encrypted viewer retry, render, thumbnails, presenter, delete/save encryption, cancel, original preservation')
