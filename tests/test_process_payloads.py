"""Complex form requests use private stdin with an explicit bounded budget."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pymupdf as pdf
from pypdf import PdfReader
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.transform_process import TransformWorker, MAX_REQUEST_BYTES


def test_complex_multiline_form_request_above_old_limit_finishes_and_keeps_values(tmp_path):
    source, target = tmp_path / 'notes.pdf', tmp_path / 'filled.pdf'
    values = {}
    text = '한글 검토 의견 ' * 110
    with pdf.open() as document:
        page = document.new_page()
        for index in range(20):
            field = pdf.Widget()
            field.field_name = f'note{index}'
            field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            field.field_flags = pdf.PDF_TX_FIELD_IS_MULTILINE
            field.rect = pdf.Rect(30, 20 + index * 38, 565, 54 + index * 38)
            widget = page.add_widget(field)
            values[str(widget.xref)] = text
        document.save(source)
    original = source.read_bytes()
    options = dict(source=str(source), target=str(target), operation='fill_forms', form_values=values)
    size = len(json.dumps(options, ensure_ascii=True).encode('utf-8'))
    assert 65536 < size < MAX_REQUEST_BYTES
    parent = QObject()
    worker = TransformWorker(options, parent)
    results = []
    worker.result.connect(lambda success, message: results.append((success, message)))
    worker.start()
    deadline = time.monotonic() + 15
    try:
        while not worker.done and time.monotonic() < deadline:
            QTest.qWait(20)
        assert worker.done and len(results) == 1 and results[0][0], results
        assert worker.temporary is None
        fields = PdfReader(target).get_fields()
        assert len(fields) == 20 and all(field['/V'] == text for field in fields.values())
        with pdf.open(target) as document:
            widgets = list(document[0].widgets())
            assert len(widgets) == 20 and all(widget.field_value == text for widget in widgets)
            assert all(document.xref_get_key(widget.xref, 'AP/N')[0] == 'xref' for widget in widgets)
            assert document[0].get_pixmap(matrix=pdf.Matrix(.5, .5)).width > 0
        assert source.read_bytes() == original
    finally:
        if worker.isRunning():
            worker.process.kill()
            worker.process.waitForFinished(1000)


def test_oversized_private_stdin_request_remains_bounded_and_does_not_publish(tmp_path):
    target = tmp_path / 'never-published.pdf'
    packet = json.dumps(dict(source='missing.pdf', target=str(target), operation='watermark_text',
                            watermark_text='x' * MAX_REQUEST_BYTES, cancel_path=str(tmp_path / 'cancel')))
    result = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--transform-child'],
                            input=packet, capture_output=True, text=True, timeout=15)
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(messages) == 1 and messages[0]['type'] == 'result' and not messages[0]['success']
    assert not target.exists()
