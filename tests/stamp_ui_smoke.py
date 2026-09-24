"""Exercise the stamp dialog through the actual isolated transform process."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtGui import QFontDatabase, QFont
from eoingpdf.advanced_ui import AdvancedDialog

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont('assets/fonts/Pretendard-Regular.ttf')
app.setFont(QFont('Pretendard', 10))
root = Path('temp/stamp-ui-test').resolve()
root.mkdir(parents=True, exist_ok=True)
source, image, target = root / 'original.pdf', root / 'seal.png', root / 'stamped.pdf'
if target.exists():
    target.unlink()
with pdf.open() as doc:
    page = doc.new_page(width=400, height=300)
    page.insert_text((40, 60), 'Stamp workflow verification')
    doc.save(source)
im = Image.new('RGB', (160, 80), 'white')
draw = ImageDraw.Draw(im)
draw.rectangle((5, 5, 155, 75), outline='red', width=6)
draw.text((60, 30), 'TEST', fill='red')
im.save(image)
from eoingpdf.seal_vault import SealVault
from eoingpdf.seal_vault_ui import SealVaultDialog
from PySide6.QtWidgets import QMessageBox
vault_temp = tempfile.TemporaryDirectory(prefix='vault-', dir=root)
vault = SealVault(Path(vault_temp.name))
with patch('eoingpdf.seal_vault_ui.QFileDialog.getOpenFileName', return_value=(str(image), 'PNG')),      patch('eoingpdf.seal_vault_ui.QInputDialog.getText', return_value=('테스트 도장', True)):
    manager = SealVaultDialog(vault=vault)
    manager.show()
    manager.add()
    QTest.qWait(60)
    assert manager.items.count() == 1 and not manager.preview.pixmap().isNull()
    manager.grab().save(str(root / 'vault.png'))
    with patch('eoingpdf.seal_vault_ui.QMessageBox.question', return_value=QMessageBox.No):
        manager.remove()
    assert manager.items.count() == 1
    manager.choose()
    encrypted_image = manager.selected_path
    assert encrypted_image and Path(encrypted_image).suffix == '.eoseal'
before = source.read_bytes()
with patch('eoingpdf.license_ui.ensure_license', return_value=True), \
     patch('eoingpdf.advanced_ui.QFileDialog.getSaveFileName', return_value=(str(target), 'PDF')):
    dialog = AdvancedDialog()
    dialog.tool.setCurrentIndex(dialog.tool.findData('stamp'))
    dialog.source.setText(str(source))
    dialog.watermark_image.setText(encrypted_image)
    dialog.stamp_x.setValue(60)
    dialog.stamp_y.setValue(30)
    dialog.show()
    QTest.qWait(100)
    assert all(field.isVisible() for field in dialog.stamp_fields)
    assert not dialog.bates_prefix.isVisible() and not dialog.watermark_opacity.isVisible()
    dialog.grab().save(str(root / 'dialog.png'))
    dialog.start()
    deadline = time.monotonic() + 30
    while dialog.worker.isRunning() and time.monotonic() < deadline:
        QTest.qWait(30)
    assert not dialog.worker.isRunning(), 'Stamp process did not finish'
    QTest.qWait(100)
    assert target.exists(), dialog.status.text()
    assert dialog.compare_button.isVisible() and dialog.save.isEnabled()
    with pdf.open(target) as result:
        assert not result[0].get_text().strip()
        assert len(result[0].get_images()) == 1
        result[0].get_pixmap(matrix=pdf.Matrix(1.5, 1.5)).save(root / 'result.png')
    assert source.read_bytes() == before
    dialog.close()
vault.remove(encrypted_image)
assert image.exists()
vault_temp.cleanup()
print('PASS: real DPAPI vault import/preview/select, stamp UI fields, isolated process, 300DPI output, comparison availability and original preservation')
