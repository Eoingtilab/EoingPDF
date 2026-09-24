import sys
import time
from pathlib import Path
import pymupdf as pdf
import pytest
from PySide6.QtCore import QCoreApplication, QObject
from PySide6.QtTest import QTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.transform_process import TransformWorker
from eoingpdf.sniffer_ui import MicroSniffer

APP = QCoreApplication.instance() or QCoreApplication([])


def wait_for(condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert condition(), 'Subprocess did not finish before the test deadline'


def source_pdf(path):
    with pdf.open() as doc:
        doc.new_page().insert_text((40, 50), 'Synthetic heading')
        doc.save(path)


def test_private_password_process_and_exit(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'encrypted.pdf'
    source_pdf(source)
    parent = QObject()
    worker = TransformWorker(dict(source=str(source), target=str(target), operation='encrypt',
                                  user_password='private-reader', owner_password='private-owner'), parent)
    results, finished = [], []
    worker.result.connect(lambda success, message: results.append((success, message)))
    worker.finished.connect(lambda: finished.append(True))
    worker.start()
    try:
        assert 'private-reader' not in ' '.join(worker.process.arguments())
        wait_for(lambda: finished)
        assert results[0][0]
        assert 'private-reader' not in results[0][1]
        assert not worker.isRunning()
        assert worker.temporary is None
        with pdf.open(target) as doc:
            assert doc.needs_pass and doc.authenticate('private-reader')
    finally:
        if worker.isRunning():
            worker.process.kill()
            worker.process.waitForFinished(1000)


def test_cancel_process_does_not_publish(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'cancelled.pdf'
    source_pdf(source)
    parent = QObject()
    worker = TransformWorker(dict(source=str(source), target=str(target), operation='flatten'), parent)
    results, finished = [], []
    worker.result.connect(lambda success, message: results.append(success))
    worker.finished.connect(lambda: finished.append(True))
    worker.start()
    worker.requestInterruption()
    try:
        wait_for(lambda: finished)
        assert results == [False]
        assert not target.exists()
        assert not worker.isRunning()
    finally:
        if worker.isRunning():
            worker.process.kill()
            worker.process.waitForFinished(1000)


def test_sniffer_real_process_returns_and_terminates(tmp_path):
    path = tmp_path / 'source.pdf'
    source_pdf(path)
    parent = QObject()
    sniffer = MicroSniffer(parent)
    results = []
    sniffer.result.connect(results.append)
    sniffer.start(path)
    try:
        wait_for(lambda: results)
        assert results[0]['pages_scanned'] == 1
        assert results[0]['total_ms'] >= results[0]['elapsed_ms']
        assert sniffer.process is None
    finally:
        sniffer.stop()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows job object integration')
def test_job_close_terminates_owned_descendant():
    import subprocess
    import win32api
    import win32con
    import win32event
    from eoingpdf.process_scope import ProcessScope
    scope = ProcessScope()
    code = ('import sys,subprocess,time;sys.stdin.readline();'
            'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],creationflags=0x08000000);'
            'print(child.pid,flush=True);time.sleep(30)')
    process = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, text=True)
    child_handle = None
    try:
        scope.assign(process.pid)
        process.stdin.write('\n')
        process.stdin.flush()
        child_pid = int(process.stdout.readline())
        child_handle = win32api.OpenProcess(win32con.SYNCHRONIZE, False, child_pid)
        scope.close()
        process.wait(timeout=3)
        assert win32event.WaitForSingleObject(child_handle, 3000) == win32event.WAIT_OBJECT_0
    finally:
        scope.close()
        if child_handle:
            child_handle.Close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        process.stdin.close()
        process.stdout.close()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows OCR worker integration')
def test_searchable_inside_owned_process_tree(tmp_path):
    source, target = tmp_path / 'scan.pdf', tmp_path / 'searchable.pdf'
    with pdf.open() as vector, pdf.open() as scan:
        page = vector.new_page(width=600, height=200)
        page.insert_text((50, 80), 'HELLO WORLD', fontsize=28)
        raster = page.get_pixmap(matrix=pdf.Matrix(2, 2))
        page = scan.new_page(width=600, height=200)
        page.insert_image(page.rect, stream=raster.tobytes('png'))
        scan.save(source)
    parent = QObject()
    worker = TransformWorker(dict(source=str(source), target=str(target), operation='searchable'), parent)
    results, finished = [], []
    worker.result.connect(lambda success, message: results.append((success, message)))
    worker.finished.connect(lambda: finished.append(True))
    worker.start()
    temporary = Path(worker.temporary.name)
    try:
        wait_for(lambda: finished, timeout=40)
        assert results[0][0], results
        assert not temporary.exists()
        with pdf.open(target) as doc:
            assert 'HELLO' in doc[0].get_text().upper()
    finally:
        if worker.isRunning():
            worker.process.kill()
            worker.process.waitForFinished(1000)
