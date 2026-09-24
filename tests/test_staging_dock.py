from pathlib import Path
import sys
import time

import pymupdf as pdf
import pytest
from PySide6.QtCore import Qt, QRect, QPoint, QMimeData, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.staging_dock import StagingDock, snapped_position
from eoingpdf.localization import install_language


def document(folder, text):
    folder.mkdir(exist_ok=True)
    path = folder / 'same.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((70, 80), text)
        doc.save(path)
    return path


def finished(dock):
    deadline = time.monotonic() + 15
    while dock.worker is not None and time.monotonic() < deadline:
        QTest.qWait(10)
    assert dock.worker is None


def test_drop_multiple_folders_reorder_merge_no_overwrite_and_originals(tmp_path, monkeypatch):
    first = document(tmp_path / '한글', 'FIRST')
    second = document(tmp_path / '日本語', 'SECOND')
    originals = [path.read_bytes() for path in (first, second)]
    dock = StagingDock()
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    try:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in (first, second, first, tmp_path)])
        mime.setUrls(mime.urls() + [QUrl('https://example.org/remote.pdf')])
        event = QDropEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        dock.dropEvent(event)
        assert event.isAccepted()
        assert dock.paths() == [str(first), str(second)]
        item = dock.files.takeItem(1)
        dock.files.insertItem(0, item)
        dock.merge()
        assert not dock.files.isEnabled()
        dock.add_files([first])  # edits are refused during a pending merge
        finished(dock)
        output = dock.output
        assert output.parent == second.parent
        with pdf.open(output) as result:
            assert [page.get_text().strip() for page in result] == ['SECOND', 'FIRST']
        content = output.read_bytes()
        dock.merge()
        finished(dock)
        assert dock.output != output and output.read_bytes() == content
        assert [path.read_bytes() for path in (first, second)] == originals
        dock.files.item(0).setSelected(True)
        dock.remove_selected()
        assert dock.paths() == [str(first)]
        dock.clear_files()
        assert not dock.dirty and not dock.merge_button.isEnabled()
    finally:
        if dock.worker is not None:
            dock.cancel()
            finished(dock)
        dock.close()


def test_bounded_collection_and_deleted_input_do_not_publish_partial_merge(tmp_path, monkeypatch):
    first = document(tmp_path / 'a', 'FIRST')
    second = document(tmp_path / 'b', 'SECOND')
    third = document(tmp_path / 'c', 'THIRD')
    dock = StagingDock()
    dock.MAX_FILES = 2
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
    try:
        dock.add_files([first, second, third])
        assert dock.paths() == [str(first), str(second)]
        second.unlink()
        dock.folder = str(tmp_path / 'result')
        dock.merge()
        finished(dock)
        assert dock.output is None and not Path(dock.folder).exists()
        assert dock.details.toPlainText()
        assert first.is_file() and third.is_file()
    finally:
        dock.close()


def test_close_cancels_running_worker_before_window_can_exit(tmp_path, monkeypatch):
    source = document(tmp_path / 'source', 'PRESERVE')
    dock = StagingDock()
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)

    def cancellable(action, files, folder, progress, cancelled):
        deadline = time.monotonic() + 5
        while not cancelled() and time.monotonic() < deadline:
            time.sleep(.005)
        return {'outputs': [], 'errors': [], 'cancelled': cancelled()}

    monkeypatch.setattr('eoingpdf.quick.execute', cancellable)
    dock.show()
    dock.add_files([source])
    dock.merge()
    assert not dock.close() and dock.isVisible()
    finished(dock)
    assert not dock.isVisible() and not dock.snap_timer.isActive()
    assert source.is_file()


def test_snaps_to_negative_coordinate_monitor_and_clamps_removed_monitor():
    available = QRect(-1920, 0, 1920, 1040)
    assert snapped_position(QRect(-1900, 640, 340, 410), available) == QPoint(-1920, 630)
    assert snapped_position(QRect(3000, 3000, 340, 410), available) == QPoint(-340, 630)
    assert snapped_position(QRect(-1400, 300, 340, 410), available) == QPoint(-1400, 300)


@pytest.mark.parametrize('locale,title', [('en-US', 'EoingPDF · Collect files'), ('ja-JP', 'EoingPDF · ファイルを集める')])
def test_localized_dock_and_process_scoped_timer(locale, title):
    app = QApplication.instance()
    previous = getattr(app, 'eoing_locale', 'ko-KR')
    install_language(app, locale)
    dock = StagingDock()
    try:
        assert dock.windowTitle() == title
        assert dock.remove_button.text() != '선택 제거'
        assert dock.clear_button.text() != '비우기'
        dock.show()
        QTest.qWait(120)
        assert dock.frameGeometry().intersects(dock.screen().availableGeometry())
        dock.close()
        assert not dock.snap_timer.isActive()
    finally:
        dock.close()
        install_language(app, previous)
