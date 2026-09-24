from pathlib import Path
import sys

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
import pymupdf as pdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.sniffer_ui import MicroSniffer


def test_print_trigger_reaches_real_diagnostic_child(tmp_path):
    from PySide6.QtCore import QEventLoop, QTimer
    source = tmp_path / 'dark-slide.pdf'
    with pdf.open() as document:
        page = document.new_page(width=300, height=180)
        page.draw_rect(page.rect, color=None, fill=(0, 0, 0))
        document.save(source)
    sniffer = MicroSniffer()
    loop = QEventLoop()
    reports = []
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    sniffer.result.connect(reports.append)
    sniffer.result.connect(loop.quit)
    try:
        sniffer.start(source, trigger='print')
        timer.start(4000)
        loop.exec()
        assert len(reports) == 1
        assert any(item['code'] == 'D-05' and item['action'] == 'print_light' for item in reports[0]['diagnostics'])
    finally:
        timer.stop()
        sniffer.stop()
        sniffer.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_cancel_and_destroy_do_not_call_deleted_qobjects(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *error: errors.append(error))
    source = tmp_path / 'source.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    for cancel in (False, True):
        parent = QWidget()
        sniffer = MicroSniffer(parent)
        sniffer.start(source)
        if cancel:
            sniffer.stop()
        parent.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QTest.qWait(80)
    assert not errors


def test_failed_start_emits_one_result_and_can_stop(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'missing-python.exe'))
    sniffer = MicroSniffer()
    reports = []
    sniffer.result.connect(reports.append)
    sniffer.start(tmp_path / 'source.pdf')
    QTest.qWait(100)
    assert len(reports) == 1 and reports[0]['diagnostics'] == []
    assert sniffer.process is None
    sniffer.stop()
    sniffer.deleteLater()
    app.processEvents()
