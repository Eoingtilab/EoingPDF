import sys
from pathlib import Path
import pymupdf as pdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.form_review_ui import FormReviewDialog
from eoingpdf.advanced import transform


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_review_exclude_and_correct_type(tmp_path, rotation):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'source.pdf'
    with pdf.open() as doc:
        page = doc.new_page(width=500, height=400)
        page.draw_rect(pdf.Rect(40, 50, 180, 80))
        page.draw_rect(pdf.Rect(40, 130, 180, 160))
        page.draw_rect(pdf.Rect(40, 210, 60, 230))
        page.set_rotation(rotation)
        doc.save(source)
    original = source.read_bytes()
    review = FormReviewDialog(source)
    review.show()
    for _ in range(300):
        QTest.qWait(10)
        if not review.scan.isRunning() and review.items.count():
            break
    assert review.items.count() == 3, review.status.text()
    assert not review.preview.pixmap().isNull()
    review.items.item(1).setCheckState(Qt.Unchecked)
    review.items.setCurrentRow(2)
    review.kind.setCurrentIndex(review.kind.findData('text'))
    review.change_kind()
    selection = review.selection()
    assert len(selection) == 2
    assert all(item['kind'] == 'text' for item in selection)
    review.apply.click()
    assert review.result() == QDialog.Accepted
    target = tmp_path / 'result.pdf'
    assert transform(source, target, 'auto_forms', form_review=selection) == 2
    with pdf.open(target) as doc:
        page = doc[0]
        fields = list(page.widgets())
        assert len(fields) == 2
        assert all(field.field_type == pdf.PDF_WIDGET_TYPE_TEXT for field in fields)
        assert page.rotation == rotation
        assert [list(field.rect) for field in fields] == [entry['rect'] for entry in selection]
    assert source.read_bytes() == original
    review.close()


def test_reject_stale_or_empty_review_without_output(tmp_path):
    source = tmp_path / 'source.pdf'
    with pdf.open() as doc:
        doc.new_page()
        doc.save(source)
    target = tmp_path / 'result.pdf'
    for entries in ([], [dict(page=0, rect=[20, 30, 120, 50], kind='text')],
                    [dict(page=4, rect=[20, 30, 120, 50], kind='checkbox')]):
        with pytest.raises(ValueError):
            transform(source, target, 'auto_forms', form_review=entries)
        assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))


def test_cancel_scan_waits_for_owned_thread(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'many.pdf'
    with pdf.open() as doc:
        for _ in range(50):
            doc.new_page().draw_rect(pdf.Rect(20, 30, 140, 60))
        doc.save(source)
    review = FormReviewDialog(source)
    review.show()
    review.reject()
    for _ in range(300):
        QTest.qWait(10)
        if not review.scan.isRunning():
            break
    app.processEvents()
    assert not review.scan.isRunning()
    assert not review.isVisible()
    assert review.result() == QDialog.Rejected



def test_advanced_dialog_review_to_worker(tmp_path, monkeypatch):
    from PySide6.QtCore import QTimer
    from eoingpdf.advanced_ui import AdvancedDialog
    app = QApplication.instance() or QApplication([])
    source, target = tmp_path / 'source.pdf', tmp_path / 'result.pdf'
    with pdf.open() as doc:
        page = doc.new_page()
        page.draw_rect(pdf.Rect(40, 50, 180, 80))
        page.draw_rect(pdf.Rect(40, 130, 180, 160))
        doc.save(source)
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *args: True)
    monkeypatch.setattr('eoingpdf.advanced_ui.QFileDialog.getSaveFileName', lambda *args: (str(target), 'PDF'))
    real_exec = FormReviewDialog.exec
    def review_exec(dialog):
        timer = QTimer(dialog)
        timer.setInterval(10)
        def choose():
            if not dialog.scan.isRunning() and dialog.items.count():
                timer.stop()
                dialog.items.item(1).setCheckState(Qt.Unchecked)
                dialog.apply.click()
        timer.timeout.connect(choose)
        timer.start()
        QTimer.singleShot(5000, dialog.reject)
        return real_exec(dialog)
    monkeypatch.setattr(FormReviewDialog, 'exec', review_exec)
    dialog = AdvancedDialog()
    dialog.source.setText(str(source))
    dialog.tool.setCurrentIndex(dialog.tool.findData('auto_forms'))
    dialog.show()
    dialog.start()
    assert dialog.worker is not None
    for _ in range(500):
        QTest.qWait(10)
        if not dialog.worker.isRunning():
            break
    assert target.exists(), dialog.status.text()
    with pdf.open(target) as doc:
        page = doc[0]
        assert len(list(page.widgets())) == 1
    dialog.close()
