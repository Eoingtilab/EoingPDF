import queue
import threading
from pathlib import Path
from unittest.mock import Mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from eoingpdf.updates import AutoUpdater


def test_backup_preparation_is_background_and_blocks_install_until_complete(monkeypatch):
    updater=object.__new__(AutoUpdater)
    updater.results=queue.Queue()
    updater.running=False
    updater.pending=None
    updater.app=Mock();updater.window=Mock();updater.timer=Mock()
    entered,release=threading.Event(),threading.Event()
    threads=[]
    def backup():
        threads.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        return Path('backup')
    monkeypatch.setattr('eoingpdf.updates.current_version',lambda:'2.2.0')
    monkeypatch.setattr('eoingpdf.updates.update_info',lambda _:dict(sha256='a'*64,version='2.3.0'))
    monkeypatch.setattr('eoingpdf.updates.download',lambda _:Path('update.exe'))
    monkeypatch.setattr('eoingpdf.updates.sys.frozen',True,raising=False)
    monkeypatch.setattr('eoingpdf.updates.backup_current_install',backup)
    monkeypatch.setattr('eoingpdf.updates.busy_window',lambda _:True)
    try:
        updater.check()
        assert entered.wait(1)
        assert updater.running and updater.pending is None
        updater.poll()
        updater.app.quit.assert_not_called()
        updater.check()
        assert len(threads)==1 and threads[0]!=threading.get_ident()
        release.set()
        result=updater.results.get(timeout=3)
        updater.results.put(result)
        updater.poll()
        assert updater.pending==Path('update.exe')
        assert updater.pending_backup==Path('backup')
        assert not updater.running
        updater.app.quit.assert_not_called()
    finally:
        release.set()


def test_backup_failure_does_not_queue_installer(monkeypatch):
    updater=object.__new__(AutoUpdater)
    updater.results=queue.Queue();updater.running=False;updater.pending=None
    monkeypatch.setattr('eoingpdf.updates.current_version',lambda:'2.2.0')
    monkeypatch.setattr('eoingpdf.updates.update_info',lambda _:dict(sha256='a'*64,version='2.3.0'))
    monkeypatch.setattr('eoingpdf.updates.download',lambda _:Path('update.exe'))
    monkeypatch.setattr('eoingpdf.updates.sys.frozen',True,raising=False)
    def failed():raise OSError('disk full')
    monkeypatch.setattr('eoingpdf.updates.backup_current_install',failed)
    updater.check()
    assert updater.results.get(timeout=3)[0] is None
