import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from eoingpdf import update_snapshot as snapshots


def fixture(tmp_path):
    install=tmp_path/'app';install.mkdir()
    (install/'EoingPDF.exe').write_bytes(b'MZ'+b'old'*1024)
    (install/'VERSION').write_text('2.2.0')
    (install/'_internal').mkdir()
    (install/'_internal'/'library.dll').write_bytes(b'old-library')
    (install/'personal.pdf').write_bytes(b'personal')
    backup=snapshots.create(install,tmp_path/'backups','2.2.0')
    (install/'EoingPDF.exe').write_bytes(b'MZ'+b'new'*1024)
    (install/'VERSION').write_text('2.3.0')
    (install/'_internal'/'library.dll').write_bytes(b'new-library')
    (install/'_internal'/'new.dll').write_bytes(b'new-only')
    return install,backup


def test_full_restore_removes_new_dependencies_preserves_user_files(tmp_path):
    install,backup=fixture(tmp_path)
    snapshots.restore(backup,install)
    assert (install/'VERSION').read_text()=='2.2.0'
    assert (install/'_internal'/'library.dll').read_bytes()==b'old-library'
    assert not (install/'_internal'/'new.dll').exists()
    assert (install/'personal.pdf').read_bytes()==b'personal'
    assert not (backup/'personal.pdf').exists()
    assert not list(install.glob('.eoing-restore-*'))


def test_mid_restore_failure_restores_current_install(tmp_path,monkeypatch):
    install,backup=fixture(tmp_path)
    replace=snapshots.os.replace
    def fail(source,target):
        if Path(source).name=='_internal' and Path(source).parent.name=='payload':
            raise PermissionError('simulated locked dependency')
        return replace(source,target)
    monkeypatch.setattr(snapshots.os,'replace',fail)
    with pytest.raises(PermissionError):snapshots.restore(backup,install)
    assert (install/'VERSION').read_text()=='2.3.0'
    assert (install/'EoingPDF.exe').read_bytes()==b'MZ'+b'new'*1024
    assert (install/'_internal'/'library.dll').read_bytes()==b'new-library'
    assert (install/'_internal'/'new.dll').exists()


def test_tampered_library_prevents_any_restore(tmp_path):
    install,backup=fixture(tmp_path)
    (backup/'_internal'/'library.dll').write_bytes(b'tampered')
    with pytest.raises(ValueError):snapshots.restore(backup,install)
    assert (install/'VERSION').read_text()=='2.3.0'
    assert not list(install.glob('.eoing-restore-*'))


def test_shell_extension_is_hashed_backed_up_and_restored(tmp_path):
    install, _ = fixture(tmp_path)
    extension = install / 'EoingPDF.Explorer.dll'
    extension.write_bytes(b'MZ-old-extension')
    backup = snapshots.create(install, tmp_path / 'shell-backups', '2.3.0')
    assert snapshots.validate(backup, install)['files']['EoingPDF.Explorer.dll'] == snapshots.digest(extension)
    extension.write_bytes(b'MZ-new-extension')
    snapshots.restore(backup, install)
    assert extension.read_bytes() == b'MZ-old-extension'
    assert (install / 'personal.pdf').read_bytes() == b'personal'


@pytest.mark.parametrize('fail_later', [False, True])
def test_rollback_removes_new_shell_root_or_restores_it_on_failure(tmp_path, monkeypatch, fail_later):
    install, backup = fixture(tmp_path)
    extension = install / 'EoingPDF.Explorer.dll'
    extension.write_bytes(b'MZ-new-only-extension')
    personal = install / 'user-plugin.dll'
    personal.write_bytes(b'personal-plugin')
    if fail_later:
        replace = snapshots.os.replace
        def fail(source, target):
            if Path(source).name == '_internal' and Path(source).parent.name == 'payload':
                raise PermissionError('locked library after shell move')
            return replace(source, target)
        monkeypatch.setattr(snapshots.os, 'replace', fail)
        with pytest.raises(PermissionError):
            snapshots.restore(backup, install)
        assert extension.read_bytes() == b'MZ-new-only-extension'
        assert (install / 'VERSION').read_text() == '2.3.0'
    else:
        snapshots.restore(backup, install)
        assert not extension.exists()
        assert (install / 'VERSION').read_text() == '2.2.0'
    assert personal.read_bytes() == b'personal-plugin'
