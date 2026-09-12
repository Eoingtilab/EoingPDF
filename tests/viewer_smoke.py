import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import hashlib
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
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
window.fill_thumbnails()
card = window.thumbnails.itemWidget(window.thumbnails.item(1))
assert card is not None
card.findChild(QPushButton, 'thumbnailPage').click()
assert window.page.value() == 2
delete_button = card.findChild(QPushButton, 'deleteThumbnail')
with patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.No):
    delete_button.click()
assert window.count == 3 and not window.dirty
with patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.Yes):
    delete_button.click()
assert window.path == source and window.count == 2 and window.dirty
assert window.pages == [0, 2] and window.save_button.isEnabled()
with pymupdf.open(source) as document:
    assert document.page_count == 3
with patch('eoingpdf.viewer.QFileDialog.getSaveFileName', return_value=('', '')):
    assert not window.save_changes() and window.dirty
with patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.Cancel):
    window.close()
assert window.isVisible() and window.dirty
window.start_slideshow()
app.processEvents()
assert window.slideshow.pages == [0, 2]
QTest.keyClick(window.slideshow, Qt.Key_Escape)
with patch('eoingpdf.viewer.QFileDialog.getSaveFileName', return_value=(str(root / 'saved.pdf'), 'PDF (*.pdf)')):
    assert window.save_changes()
assert window.path != source and window.count == 2
assert not window.dirty and not window.save_button.isEnabled()
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
window.fill_thumbnails()
window.grab().save(str(root / 'viewer.png'))
window.load(source)
window.page.setValue(2)
window.start_slideshow()
app.processEvents()
slides = window.slideshow
assert slides.isFullScreen() and slides.index == 1
assert not slides.canvas.pixmap().isNull()
QTest.keyClick(slides, Qt.Key_Space)
assert slides.index == 2
QTest.keyClick(slides, Qt.Key_Right)
assert slides.index == 2
QTest.keyClick(slides, Qt.Key_Left)
assert slides.index == 1
QTest.mouseClick(slides.canvas, Qt.LeftButton)
assert slides.index == 2
QTest.mouseClick(slides.canvas, Qt.RightButton)
assert slides.index == 1
QTest.keyClick(slides, Qt.Key_Home)
assert slides.index == 0
QTest.keyClick(slides, Qt.Key_End)
assert slides.index == 2
slides.grab().save(str(root / 'slideshow.png'))
QTest.keyClick(slides, Qt.Key_Escape)
app.processEvents()
assert not slides.isVisible() and window.page.value() == 3
window.start_slideshow()
app.processEvents()
slides = window.slideshow
window.start_slideshow()
assert window.slideshow is slides
QTest.mouseClick(slides.exit_button, Qt.LeftButton)
app.processEvents()
assert not slides.isVisible() and window.isVisible()
window.start_slideshow()
app.processEvents()
QTest.keyClick(window.slideshow, Qt.Key_F5)
app.processEvents()
assert not window.slideshow.isVisible()
window.showMaximized()
app.processEvents()
with patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.Yes):
    window.stage_delete({1})
with patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.Cancel) as question:
    window.close_button.click()
    assert question.call_count == 1 and window.isVisible()
with patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.Discard) as question:
    window.close_button.click()
    assert question.call_count == 1 and not window.isVisible()
assert hashlib.sha256(source.read_bytes()).hexdigest() == before
window.close()
print('PASS: viewer rendering, navigation, zoom, UI deletion of middle page, original preserved, all-page deletion rejected')
print('PASS: thumbnail click and X, cancel/confirm deletion, deferred save, cancelled save and close, draft slideshow mapping')
print('PASS: fullscreen slideshow, current-page start, Space/arrows/mouse, boundaries, Home/End, Escape returns to page')
print('PASS: fullscreen exit button/F5, no duplicate slideshow, maximized viewer close/cancel with one confirmation')
