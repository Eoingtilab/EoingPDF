import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import hashlib
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from eoingpdf.viewer import PdfViewer, delete_pages
from eoingpdf.convert import text_pdf, ROOT

app = QApplication([])
QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
app.setFont(QFont('Pretendard', 10))
root = ROOT / 'temp/viewer-test'
root.mkdir(parents=True, exist_ok=True)
source = root / '원본.pdf'
with pymupdf.open() as document:
    for number in range(1, 4):
        document.new_page().insert_text((48, 48), f'Page {number}: PDF viewer and middle-page deletion test.')
    document.save(source)
before = hashlib.sha256(source.read_bytes()).hexdigest()
window = PdfViewer(source)
window.show()
app.processEvents()
assert not window.canvas.pixmap().isNull()
window.page.setValue(2)
assert window.previous.isEnabled() and window.next.isEnabled()
window.zoom.setCurrentText('150%')
app.processEvents()
assert window.canvas.pixmap().width() > 800
with patch('eoingpdf.viewer.QInputDialog.getText', return_value=('2', True)), patch('eoingpdf.viewer.QFileDialog.getExistingDirectory', return_value=str(root)):
    window.remove_pages()
assert window.path != source and window.count == 2
with pymupdf.open(window.path) as document:
    assert 'Page 1' in document[0].get_text()
    assert 'Page 3' in document[1].get_text()
assert hashlib.sha256(source.read_bytes()).hexdigest() == before
try:
    delete_pages(source, '1-3', root)
    raise AssertionError('Must reject deleting all pages')
except ValueError:
    pass
window.zoom.setCurrentIndex(0)
app.processEvents()
window.grab().save(str(root / 'viewer.png'))
window.close()
print('PASS: viewer rendering, navigation, zoom, UI deletion of middle page, original preserved, all-page deletion rejected')
