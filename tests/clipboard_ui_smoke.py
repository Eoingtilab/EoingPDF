"""Real Qt drag/button flow with clipboard publication replaced by a test sink."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
from unittest.mock import patch
import pymupdf as pdf
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.app import STYLE
from eoingpdf.viewer import PdfViewer

folder = ROOT / 'temp/clipboard-ui'
folder.mkdir(parents=True, exist_ok=True)
source = folder / 'table.pdf'
with pdf.open() as doc:
    page = doc.new_page(width=400, height=300)
    for x in (50, 150, 250):
        page.draw_line((x, 50), (x, 150))
    for y in (50, 100, 150):
        page.draw_line((50, y), (250, y))
    for x, y, text in [(60, 80, 'A'), (160, 80, 'B'), (60, 130, '1'), (160, 130, '2')]:
        page.insert_text((x, y), text)
    doc.save(source)
app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
app.setFont(QFont('Pretendard', 10))
viewer = PdfViewer(source)
viewer.show()
QTest.qWait(200)
with patch('eoingpdf.license_ui.ensure_license', return_value=True), \
     patch('eoingpdf.clipboard_tools.copy_table') as copy_table, \
     patch('eoingpdf.clipboard_tools.copy_page') as copy_page:
    QTest.mouseClick(viewer.table_copy_button, Qt.LeftButton)
    assert viewer.canvas.selecting
    sx, sy = viewer.canvas.width() / 400, viewer.canvas.height() / 300
    start = QPoint(round(40 * sx), round(40 * sy))
    end = QPoint(round(260 * sx), round(160 * sy))
    QTest.mousePress(viewer.canvas, Qt.LeftButton, pos=start)
    QTest.mouseMove(viewer.canvas, end)
    QTest.mouseRelease(viewer.canvas, Qt.LeftButton, pos=end)
    QTest.qWait(100)
    assert copy_table.call_count == 1
    assert copy_table.call_args.args[0] == [['A', 'B'], ['1', '2']]
    assert '2행' in viewer.status.text(), repr(viewer.status.text())
    QTest.mouseClick(viewer.copy_image_button, Qt.LeftButton)
    assert copy_page.call_count == 1
    assert '300DPI' in viewer.status.text()
viewer.close()
print('PASS: actual Qt table drag and page-copy button; clipboard left untouched')

