import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf import distribution, updates


@pytest.fixture
def portable(tmp_path, monkeypatch):
    bundle = tmp_path / 'temporary-extraction'
    (bundle / 'portable_tools').mkdir(parents=True)
    (bundle / 'assets').mkdir()
    (bundle / 'onefile.marker').write_text('onefile')
    (bundle / 'portable_tools/EoingPDF.Shell.exe').write_bytes(b'MZ-bridge')
    (bundle / 'assets/pdf_icon.ico').write_bytes(b'icon')
    executable = tmp_path / '어잉 portable.exe'
    executable.write_bytes(b'MZ-portable' + b'0' * 2048)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(bundle), raising=False)
    monkeypatch.setattr(sys, 'executable', str(executable))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    return bundle, executable


def test_single_file_registration_paths_survive_extraction_and_preserve_exe_name(portable):
    bundle, executable = portable
    layout = distribution.shell_layout()
    assert not layout.bridge.exists()  # reading status must not install helpers
    assert layout.executable == executable
    assert layout.portable
    assert str(executable) in layout.command('merge')
    assert str(bundle) not in layout.command('merge')
    prepared = distribution.shell_layout(prepare=True)
    assert prepared == layout
    assert prepared.bridge.read_bytes() == b'MZ-bridge'
    assert prepared.icon.read_bytes() == b'icon'
    assert distribution.shell_layout(prepare=True) == prepared


def test_portable_unregistration_keeps_user_files_and_other_copies(portable, monkeypatch):
    _, executable = portable
    first = distribution.shell_layout(prepare=True)
    user = first.bridge.parent / 'user.pdf'
    user.write_bytes(b'user')
    second_exe = executable.with_name('other.exe')
    second_exe.write_bytes(b'MZ-other')
    monkeypatch.setattr(sys, 'executable', str(second_exe))
    second = distribution.shell_layout(prepare=True)
    monkeypatch.setattr(sys, 'executable', str(executable))
    distribution.cleanup_portable_shell()
    assert not first.bridge.exists() and not first.icon.exists()
    assert user.read_bytes() == b'user'
    assert second.bridge.is_file() and second_exe.is_file() and executable.is_file()


def test_changed_helper_is_repaired_only_at_registration(portable):
    layout = distribution.shell_layout(prepare=True)
    layout.bridge.write_bytes(b'changed')
    distribution.cleanup_portable_shell()
    assert layout.bridge.read_bytes() == b'changed'
    distribution.shell_layout(prepare=True)
    assert layout.bridge.read_bytes() == b'MZ-bridge'


@pytest.mark.parametrize('invalid', [[], 42, {'files': []}, {'executable': 'other'}])
def test_malformed_or_foreign_ownership_is_preserved(portable, invalid):
    layout = distribution.shell_layout(prepare=True)
    (layout.bridge.parent / 'owner.json').write_text(json.dumps(invalid))
    distribution.cleanup_portable_shell()
    assert layout.bridge.exists()


def test_bundled_helper_update_has_separate_cache(portable):
    bundle, _ = portable
    first = distribution.shell_layout(prepare=True)
    (bundle / 'portable_tools/EoingPDF.Shell.exe').write_bytes(b'MZ-new-bridge')
    second = distribution.shell_layout(prepare=True)
    assert first.bridge != second.bridge
    assert first.bridge.read_bytes() == b'MZ-bridge'
    assert second.bridge.read_bytes() == b'MZ-new-bridge'
    distribution.cleanup_portable_shell()
    assert not first.bridge.exists() and not second.bridge.exists()


def test_directory_distribution_retains_existing_layout(tmp_path):
    layout = distribution.shell_layout(tmp_path)
    assert not layout.portable
    assert layout.command('merge') == f'"{tmp_path / "EoingPDF.Shell.exe"}" merge'
    assert layout.icon == tmp_path / '_internal/assets/pdf_icon.ico'


def test_single_file_version_is_embedded_and_never_backs_up_neighbor_files(portable):
    bundle, executable = portable
    (bundle / 'VERSION').write_text('2.2.0')
    (executable.parent / 'VERSION').write_text('99.0.0')
    assert updates.current_version() == '2.2.0'
    assert updates.latest_backup() is None
    backup = updates.backup_current_install()
    assert (backup / 'EoingPDF.exe').read_bytes() == executable.read_bytes()
    assert sorted(p.name for p in backup.iterdir()) == ['EoingPDF.exe', 'manifest.json']
    assert updates.latest_backup() == (backup, '2.2.0')
    assert (executable.parent / 'VERSION').read_text() == '99.0.0'


def test_single_file_does_not_fall_back_to_folder_installer(portable, monkeypatch):
    from unittest.mock import Mock
    from eoingpdf.licensing import LicenseError
    (portable[0] / 'VERSION').write_text('2.2.0')
    monkeypatch.setattr(updates, 'store', lambda: Mock(data={'key': 'test', 'device': 'test'}))
    response = dict(new_version='2.3.0', download_link='https://app.nal.la/setup.exe', sha256='a'*64)
    monkeypatch.setattr(updates, 'request', lambda *args: response)
    with pytest.raises(LicenseError, match='단일 EXE'):
        updates.update_info('2.2.0')
    response.update(portable_download_link='https://app.nal.la/portable.exe', portable_sha256='b'*64)
    assert updates.update_info('2.2.0') == dict(version='2.3.0', url=response['portable_download_link'], sha256='b'*64)
