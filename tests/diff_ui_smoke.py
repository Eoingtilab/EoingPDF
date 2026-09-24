"""Pixel-level checks of real Qt overlay controls; synthetic documents only."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
import pymupdf as pdf
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.app import STYLE
from eoingpdf.diff_ui import DiffDialog

folder = ROOT / 'temp/diff-ui'
folder.mkdir(parents=True, exist_ok=True)
before, after = folder / 'before.pdf', folder / 'after.pdf'
for path, left, count in ((before, 20, 1), (after, 100, 2)):
    with pdf.open() as doc:
        for _ in range(count):
            page = doc.new_page(width=200, height=120)
            page.draw_rect(pdf.Rect(left, 20, left + 40, 50), color=(0, 0, 0), fill=(0, 0, 0))
        doc.save(path)
app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
app.setFont(QFont('Pretendard', 10))
dialog = DiffDialog(before=before, after=after)
dialog.show()
QTest.qWait(200)
assert dialog.canvas.images and dialog.page.maximum() == 2

def pixel():
    QTest.qWait(30)
    color = dialog.canvas.grab().toImage().pixelColor(60, 60)
    return color.red(), color.green(), color.blue()

assert pixel() == (215, 50, 65)
dialog.mode.setCurrentIndex(1)
dialog.slider.setValue(0)
assert pixel() == (255, 255, 255)
dialog.slider.setValue(100)
assert pixel() == (0, 0, 0)
dialog.mode.setCurrentIndex(2)
dialog.slider.setValue(0)
assert pixel() == (0, 0, 0)
dialog.slider.setValue(100)
assert pixel() == (255, 255, 255)
dialog.page.setValue(2)
assert '원본에 없는' in dialog.status.text()
dialog.grab().save(str(folder / 'comparison.png'))
dialog.paths[0] = folder / 'missing.pdf'
dialog.load_paths()
assert dialog.canvas.images is None
assert '열지 못했습니다' in dialog.status.text()
dialog.close()
print('PASS: difference colors, slider endpoints, overlay endpoints, missing page, stale-result clearing')
