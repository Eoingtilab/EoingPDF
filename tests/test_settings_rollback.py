import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from unittest.mock import patch
import pymupdf as pdf
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from eoingpdf.settings_ui import SettingsDialog
from eoingpdf.updates import backup_current_install, latest_backup

def test_settings_shows_rollback_backup(tmp_path):
    app = QApplication.instance() or QApplication([])
    install = tmp_path / 'app'; install.mkdir()
    executable = install / 'EoingPDF.exe'; executable.write_bytes(b'MZ' + b'x' * 2048)
    (install / 'VERSION').write_text('2.2.0', encoding='utf-8')
    local = tmp_path / 'local'
    with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}), patch('eoingpdf.updates.sys.frozen', True, create=True), patch('eoingpdf.updates.current_version', return_value='2.2.0'), patch('eoingpdf.updates.sys.executable', str(executable)):
        backup_current_install(install)
        assert latest_backup(install)[1] == '2.2.0'
        dialog = SettingsDialog()
        dialog.show()
        for _ in range(100):
            QTest.qWait(10)
            dialog.refresh()
            if dialog.rollback_button.isEnabled():
                break
        assert dialog.rollback_button.isEnabled()
        assert '2.2.0' in dialog.rollback_status.text()
        dialog.close()


def test_backup_scan_does_not_block_or_repeat_on_refresh(monkeypatch):
    import threading
    app = QApplication.instance() or QApplication([])
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def slow_backup():
        calls.append(threading.get_ident())
        started.set()
        release.wait(5)
        finished.set()
        return (Path('verified-backup'), '2.2.0')
    monkeypatch.setattr('eoingpdf.settings_ui.latest_backup', slow_backup)
    dialog = SettingsDialog()
    try:
        dialog.show()
        assert started.wait(1)
        assert not finished.is_set()
        assert not dialog.rollback_button.isEnabled()
        for _ in range(10):
            dialog.refresh()
            app.processEvents()
        assert len(calls) == 1
        assert calls[0] != threading.get_ident()
        dialog.close()
        assert not dialog.timer.isActive()
        release.set()
        assert finished.wait(1)
        # Reopening explicitly checks again, rather than keeping a stale result.
        dialog.show()
        for _ in range(100):
            QTest.qWait(10)
            dialog.refresh()
            if dialog.rollback_button.isEnabled():
                break
        assert dialog.rollback_button.isEnabled()
        assert len(calls) == 2
    finally:
        release.set()
        dialog.close()
