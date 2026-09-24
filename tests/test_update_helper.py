import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from eoingpdf import update_snapshot as snapshot
from eoingpdf import update_helper as helper


@pytest.mark.skipif(os.name!='nt',reason='Windows process handle test')
def test_helper_waits_for_parent_then_restores(tmp_path):
    install=tmp_path/'app';install.mkdir()
    (install/'EoingPDF.exe').write_bytes(b'MZ'+b'old'*1024)
    (install/'VERSION').write_text('2.2.0')
    backup=snapshot.create(install,tmp_path/'backups','2.2.0')
    (install/'VERSION').write_text('2.3.0')
    report=tmp_path/'status.json'
    parent=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW)
    child=None
    try:
        packet=dict(backup=str(backup),install=str(install),report=str(report),pid=parent.pid,restart=False)
        child=subprocess.Popen([sys.executable,'main.py','--maintenance-child'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        child.stdin.write(json.dumps(packet).encode());child.stdin.close();child.stdin=None
        for _ in range(200):
            state = helper.read_status(report)
            if state is not None:break
            assert child.poll() is None
            time.sleep(.025)
        assert state is not None and state['state']=='ready'
        report.with_suffix('.go').write_text('restore')
        time.sleep(.15)
        assert (install/'VERSION').read_text()=='2.3.0'
        assert child.poll() is None
        parent.terminate();parent.wait(timeout=5)
        stdout,stderr=child.communicate(timeout=10)
        assert child.returncode==0,(stdout,stderr,report.read_text(encoding='utf-8'))
        assert json.loads(report.read_text(encoding='utf-8'))['state']=='restored'
        assert (install/'VERSION').read_text()=='2.2.0'
    finally:
        for owned in (child,parent):
            if owned and owned.poll() is None:
                owned.terminate();owned.wait(timeout=5)


def test_helper_invalid_manifest_never_modifies_install(tmp_path):
    install=tmp_path/'app';install.mkdir()
    (install/'VERSION').write_text('2.3.0')
    backup=tmp_path/'invalid';backup.mkdir()
    report=tmp_path/'status.json'
    packet=dict(backup=str(backup),install=str(install),report=str(report),pid=os.getpid(),restart=False)
    result=subprocess.run([sys.executable,'main.py','--maintenance-child'],input=json.dumps(packet).encode(),capture_output=True,timeout=10)
    assert result.returncode==1
    assert json.loads(report.read_text(encoding='utf-8'))['state']=='failed'
    assert (install/'VERSION').read_text()=='2.3.0'


@pytest.mark.parametrize('exit_code,healthy', [(0, True), (20, True), (0, False)])
def test_installer_process_success_or_failure_restoration(tmp_path, monkeypatch, exit_code, healthy):
    import hashlib
    from eoingpdf import update_helper as helper
    install=tmp_path/'app';install.mkdir()
    (install/'EoingPDF.exe').write_bytes(b'MZ'+b'old'*1024)
    (install/'VERSION').write_text('2.2.0')
    (install/'_internal').mkdir()
    (install/'_internal'/'library.dll').write_bytes(b'old-library')
    backup=snapshot.create(install,tmp_path/'backups','2.2.0')
    installer=tmp_path/'installer.exe'
    installer.write_bytes(b'MZ'+b'installer'*1024)
    packet=dict(installer=str(installer),digest=hashlib.sha256(installer.read_bytes()).hexdigest(),report=str(tmp_path/'status.json'))
    real_popen=subprocess.Popen
    commands=[]
    def spawn(command, **kwargs):
        commands.append(command)
        code="from pathlib import Path; import sys; p=Path(sys.argv[1]); (p/'VERSION').write_text('2.3.0'); (p/'_internal'/'library.dll').write_bytes(b'new-library'); sys.exit(int(sys.argv[2]))"
        return real_popen([sys.executable,'-c',code,str(install),str(exit_code)],**kwargs)
    monkeypatch.setattr(helper.subprocess,'Popen',spawn)
    monkeypatch.setattr(helper, 'runtime_healthy', lambda folder: healthy)
    result=helper.install_update(packet,install,backup)
    assert '/HELPERMANAGED=1' in commands[0]
    success = exit_code == 0 and healthy
    assert result==('updated' if success else 'restored')
    assert (install/'VERSION').read_text()==('2.3.0' if success else '2.2.0')
    assert (install/'_internal'/'library.dll').read_bytes()==(b'new-library' if success else b'old-library')


def test_still_running_installer_does_not_trigger_restore(tmp_path,monkeypatch):
    import hashlib
    from unittest.mock import Mock
    from eoingpdf import update_helper as helper
    install=tmp_path/'app';install.mkdir()
    (install/'VERSION').write_text('2.3.0')
    installer=tmp_path/'installer.exe';installer.write_bytes(b'MZ'+b'installer'*1024)
    process=Mock()
    process.wait.side_effect=subprocess.TimeoutExpired('installer',900)
    monkeypatch.setattr(helper.subprocess,'Popen',lambda *args,**kwargs:process)
    restore=Mock();monkeypatch.setattr(helper,'restore',restore)
    packet=dict(installer=str(installer),digest=hashlib.sha256(installer.read_bytes()).hexdigest(),report=str(tmp_path/'status.json'))
    with pytest.raises(subprocess.TimeoutExpired):helper.install_update(packet,install,tmp_path/'backup')
    restore.assert_not_called()
    process.kill.assert_not_called()
    assert (install/'VERSION').read_text()=='2.3.0'


def test_status_reader_treats_transient_sharing_violation_as_pending(tmp_path, monkeypatch):
    report = tmp_path / 'status.json'
    helper.write_status(report, 'ready')
    original = Path.open
    calls = []
    def blocked_once(path, *args, **kwargs):
        if path == report and not calls:
            calls.append(path)
            raise PermissionError('sharing violation')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', blocked_once)
    assert helper.read_status(report) is None
    assert helper.read_status(report)['state'] == 'ready'


@pytest.mark.parametrize('permanent', [False, True])
def test_status_writer_retries_without_losing_previous_state(tmp_path, monkeypatch, permanent):
    report = tmp_path / 'status.json'
    helper.write_status(report, 'ready')
    original = os.replace
    attempts = []
    def blocked(source, target):
        attempts.append(1)
        assert helper.read_status(report)['state'] == 'ready'
        if permanent or len(attempts) < 3:
            raise PermissionError('sharing violation')
        return original(source, target)
    monkeypatch.setattr(helper.os, 'replace', blocked)
    monkeypatch.setattr(helper.time, 'sleep', lambda delay: None)
    if permanent:
        with pytest.raises(PermissionError):
            helper.write_status(report, 'restored')
        assert len(attempts) == 21
        assert helper.read_status(report)['state'] == 'ready'
    else:
        helper.write_status(report, 'restored')
        assert len(attempts) == 3
        assert helper.read_status(report)['state'] == 'restored'
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('content', [b'[]', b'{"state": 1}', b'{"state":"ready","message":null}', b'x' * 65537],
                         ids=['array', 'invalid-state', 'invalid-message', 'oversized'])
def test_invalid_status_never_authorizes_update(tmp_path, content):
    report = tmp_path / 'status.json'
    report.write_bytes(content)
    with pytest.raises(ValueError):
        helper.read_status(report)
    assert not report.with_suffix('.go').exists()
