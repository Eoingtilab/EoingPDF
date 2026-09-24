import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QFont
from eoingpdf.app import Window, STYLE, ROOT
from eoingpdf.viewer import PdfViewer
from eoingpdf.localization import install_korean

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
assert QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf')) >= 0
app.setFont(QFont('Pretendard', 10))
install_korean(app)
root = ROOT / 'temp/ui-regressions'
root.mkdir(parents=True, exist_ok=True)
source = root / 'landscape.pdf'
with pymupdf.open() as doc:
    for _ in range(2):
        doc.new_page(width=960, height=540)
    doc.save(source)
viewer = PdfViewer(source)
viewer.show()
QTest.qWait(150)
first = viewer.canvas.width()
assert abs(first - (viewer.scroll.viewport().width() - 30)) <= 2
viewer.page.setValue(2)
QTest.qWait(150)
assert viewer.canvas.width() == first
viewer.resize(1200, 850)
QTest.qWait(150)
assert abs(viewer.canvas.width() - (viewer.scroll.viewport().width() - 30)) <= 2
up = next(b for b in viewer.findChildren(QPushButton) if b.text() == '▲')
down = next(b for b in viewer.findChildren(QPushButton) if b.text() == '▼')
QTest.mouseClick(down, Qt.LeftButton)
assert viewer.page.value() == 1
QTest.mouseClick(up, Qt.LeftButton)
assert viewer.page.value() == 2
box = QMessageBox()
box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
texts = [box.button(b).text() for b in (QMessageBox.Save, QMessageBox.Discard, QMessageBox.Cancel)]
assert all(not any(word in t for word in ('Save', 'Discard', 'Cancel')) for t in texts), texts
viewer.close()
window = Window()
window.resize(1040, 740)
window.show()
window.select_tool('rotate')
QTest.qWait(100)
choose = window.findChild(QPushButton, 'chooseFiles')
assert choose.height() >= 38 and choose.isVisible() and '파일 선택' in choose.text()
window.grab().save(str(root / 'rotate.png'))
window.close()
from eoingpdf.advanced_ui import AdvancedDialog
advanced = AdvancedDialog()
advanced.show()
QTest.qWait(100)
assert advanced.user_password.isEnabled()
advanced.tool.setCurrentIndex(advanced.tool.findData('redact'))
QTest.qWait(100)
assert not advanced.user_password.isEnabled()
assert '스캔' in advanced.description.text()
assert advanced.save.isVisible() and advanced.save.height() >= 30
advanced.grab().save(str(root / 'advanced.png'))
advanced.tool.setCurrentIndex(advanced.tool.findData('watermark_text'))
QTest.qWait(100)
assert advanced.watermark_text.isVisible() and advanced.watermark_opacity.isVisible()
assert not advanced.image_row.isVisible()
advanced.tool.setCurrentIndex(advanced.tool.findData('watermark_png'))
QTest.qWait(100)
assert advanced.image_row.isVisible() and not advanced.watermark_text.isVisible()
advanced.tool.setCurrentIndex(advanced.tool.findData('split_ranges'))
QTest.qWait(100)
assert advanced.split_ranges.isVisible() and 'ZIP' in advanced.save.text()
assert not advanced.group_size.isVisible()
advanced.tool.setCurrentIndex(advanced.tool.findData('split_groups'))
QTest.qWait(100)
assert advanced.group_size.isVisible() and not advanced.split_ranges.isVisible()
advanced.tool.setCurrentIndex(advanced.tool.findData('target_size'))
QTest.qWait(100)
assert advanced.target_mb.isVisible() and advanced.size_presets.isVisible()
advanced.size_presets.setCurrentIndex(1)
assert advanced.target_mb.value() == 25
advanced.target_mb.setValue(12.5)
assert advanced.size_presets.currentIndex() == 2
advanced.target_mb.setValue(10)
assert advanced.size_presets.currentIndex() == 0
advanced.close()
recovery = AdvancedDialog()
recovery.tool.setCurrentIndex(recovery.tool.findData('repair'))
recovery.show()
QTest.qWait(50)
assert '교차 참조' in recovery.description.text()
assert not recovery.target_mb.isVisible() and not recovery.split_ranges.isVisible()
assert not recovery.user_password.isEnabled()
recovery.close()
markdown = AdvancedDialog()
markdown.tool.setCurrentIndex(markdown.tool.findData('markdown'))
markdown.show()
QTest.qWait(50)
assert markdown.save.text() == 'Markdown 저장'
assert not markdown.target_mb.isVisible() and not markdown.split_ranges.isVisible()
markdown.close()
print_layout = AdvancedDialog()
print_layout.tool.setCurrentIndex(print_layout.tool.findData('booklet'))
print_layout.show()
QTest.qWait(50)
assert '짧은 쪽' in print_layout.description.text()
assert print_layout.save.text() == '새 PDF로 저장'
assert not print_layout.target_mb.isVisible()
print_layout.close()
svg = AdvancedDialog()
svg.tool.setCurrentIndex(svg.tool.findData('svg'))
svg.show()
QTest.qWait(40)
assert svg.save.text() == 'SVG ZIP 저장'
assert not svg.split_ranges.isVisible() and not svg.target_mb.isVisible()
svg.close()
roll = AdvancedDialog()
roll.tool.setCurrentIndex(roll.tool.findData('slice_a4'))
roll.show()
QTest.qWait(40)
assert '축소' in roll.description.text() and roll.save.text() == '새 PDF로 저장'
assert not roll.split_ranges.isVisible() and not roll.target_mb.isVisible()
roll.close()
forms = AdvancedDialog()
forms.tool.setCurrentIndex(forms.tool.findData('auto_forms'))
forms.show()
QTest.qWait(40)
assert '양식 지원 뷰어' in forms.description.text()
assert forms.save.text() == '새 PDF로 저장'
forms.close()
bates = AdvancedDialog()
bates.tool.setCurrentIndex(bates.tool.findData('bates'))
bates.show()
QTest.qWait(40)
assert all(field.isVisible() for field in bates.bates_fields)
assert bates.bates_start.value() == 1 and bates.bates_digits.value() == 6
bates.tool.setCurrentIndex(bates.tool.findData('encrypt'))
assert all(not field.isVisible() for field in bates.bates_fields)
bates.close()
print('PASS: initial/next/resized width fit; page arrows; Korean standard buttons; rotation file button at small size')
