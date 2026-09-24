import json
from pathlib import Path
import sys
import time
import pymupdf as pdf
import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.search_worker import SearchWorker


def execute(options, cancel=False, cancel_embedding=False):
    parent = QObject()
    class ControlledWorker(SearchWorker):
        def launch(self):
            super().launch()
            if cancel_embedding and self.phase == 'complete':
                self.requestInterruption()
    worker = ControlledWorker(dict(options), parent)
    results, finished, stages = [], [], []
    worker.progress.connect(lambda value: stages.append(worker.phase))
    worker.result.connect(lambda ok, message: results.append((ok, message)))
    worker.finished.connect(lambda: finished.append(True))
    worker.start()
    if cancel:
        worker.requestInterruption()
    deadline = time.monotonic() + 15
    try:
        while not finished and time.monotonic() < deadline:
            QTest.qWait(20)
        assert finished and len(results) == 1
        assert not worker.isRunning()
        assert worker.temporary is None
        assert not worker.cancel_timer.isActive()
        if options.get('mode') == 'build' and results[0][0]:
            assert 'prepare' in stages and 'complete' in stages
            assert not list(Path(options['database']).parent.glob('eoing-index-*'))
        return results[0]
    finally:
        if worker.isRunning():
            worker.process.kill()
            worker.process.waitForFinished(5000)
        parent.deleteLater()


def test_real_child_build_search_and_cancel(tmp_path):
    model = ROOT / 'temp/search-model'
    if not (model / 'model.onnx').exists():
        pytest.skip('Prepare the real search evaluation model first')
    folder = tmp_path / 'docs'; folder.mkdir()
    source = folder / 'guide.pdf'
    with pdf.open() as document:
        document.new_page().insert_text((72, 72), 'Reset your password using email verification.')
        document.save(source)
    original = source.read_bytes()
    options = dict(mode='build', model_folder=str(model), folder=str(folder), database=str(tmp_path / 'search.db'))
    ok, message = execute(options)
    assert ok, message
    assert json.loads(message)['updated'] == 1
    ok, message = execute(dict(options, mode='search', query='Forgot account credentials'))
    assert ok, message
    assert json.loads(message)[0]['path'] == str(source.resolve())
    ok, message = execute(options, cancel=True)
    assert not ok and '취소' in message
    assert source.read_bytes() == original
    previous = Path(options['database']).read_bytes()
    with pdf.open() as document:
        document.new_page().insert_text((72, 72), 'New policy replaces the old password procedure.')
        document.save(source)
    ok, message = execute(options, cancel_embedding=True)
    assert not ok and '취소' in message
    assert Path(options['database']).read_bytes() == previous
    assert not list(tmp_path.glob('eoing-index-*'))


def test_invalid_operation_reports_failure_and_exits(tmp_path):
    ok, message = execute(dict(mode='unknown'))
    assert not ok and '지원하지' in message


def test_unwritable_staging_reports_failure_without_starting_child(tmp_path):
    parent = QObject()
    blocker = tmp_path / 'file'
    blocker.write_text('preserve')
    worker = SearchWorker(dict(mode='build', database=str(blocker / 'search.db')), parent)
    results, finished = [], []
    worker.result.connect(lambda ok, message: results.append((ok, message)))
    worker.finished.connect(lambda: finished.append(True))
    worker.start()
    assert finished and len(results) == 1 and not results[0][0]
    assert worker.child is None and not worker.isRunning()
    assert blocker.read_text() == 'preserve'
    parent.deleteLater()
