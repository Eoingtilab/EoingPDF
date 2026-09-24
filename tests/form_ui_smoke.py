import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import pymupdf as pdf
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.form_ui import FormDialog

app = QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory(prefix='form-ui-', dir=ROOT / 'temp') as temporary:
    folder = Path(temporary)
    source, target = folder / 'source.pdf', folder / 'filled.pdf'
    with pdf.open() as document:
        page = document.new_page()
        for kind, name, rect in ((pdf.PDF_WIDGET_TYPE_TEXT, 'Name', (40, 40, 250, 80)),
                                 (pdf.PDF_WIDGET_TYPE_CHECKBOX, 'Accept', (40, 100, 60, 120))):
            field = pdf.Widget()
            field.field_type, field.field_name, field.rect = kind, name, pdf.Rect(rect)
            page.add_widget(field)
        document.save(source)
    original = source.read_bytes()
    dialog = FormDialog(source, 0)
    saved = []
    dialog.saved.connect(saved.append)
    dialog.show()
    for field in dialog.fields.values():
        if isinstance(field, QCheckBox):
            field.setChecked(True)
        else:
            field.setText('홍길동')
    with patch('eoingpdf.license_ui.ensure_license', return_value=True), patch(
            'eoingpdf.form_ui.QFileDialog.getSaveFileName', return_value=(str(target), 'PDF')):
        dialog.save.click()
    for _ in range(300):
        if not dialog.isVisible():
            break
        QTest.qWait(20)
    assert saved == [str(target)] and not dialog.isVisible()
    with pdf.open(target) as document:
        page = document[0]
        assert '홍길동' in page.get_text()
        values = {field.field_name: field.field_value for field in page.widgets()}
        assert values == {'Name': '홍길동', 'Accept': 'Yes'}
        image = ROOT / 'temp/form-filled-korean.png'
        page.get_pixmap().save(image)
    assert source.read_bytes() == original
print('PASS: real form dialog to worker to PDF, Korean text and checkbox persistence, source preserved')
