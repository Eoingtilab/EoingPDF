"""Inspect real generated CArchives without launching an app or contacting a server."""
import builtins
import importlib.util
from pathlib import Path

from PyInstaller.archive.writers import CArchiveWriter
import pytest


SPEC = importlib.util.spec_from_file_location('frozen_license_smoke', Path(__file__).with_name('frozen_license_smoke.py'))
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


@pytest.fixture
def sources(tmp_path, monkeypatch):
    folder = tmp_path / 'python-runtime'
    folder.mkdir()
    names = ('_ssl.pyd', 'libcrypto-3-x64.dll', 'libssl-3-x64.dll', 'codex-rejected-cas.pem')
    paths = []
    for name in names:
        path = folder / name
        path.write_bytes(('canonical fixture: ' + name).encode())
        paths.append(path)
    monkeypatch.setattr(smoke, 'python_tls_sources', lambda: paths)
    return paths


def archive(tmp_path, sources, *, omitted=(), replacements=None, extras=None, marker=True):
    entries = []
    replacements = replacements or {}
    for source in sources:
        if source.name in omitted:
            continue
        if source.name in replacements:
            replacement = tmp_path / ('replacement-' + source.name)
            replacement.write_bytes(replacements[source.name])
            source_path = replacement
        else:
            source_path = source
        entries.append((source.name, str(source_path), True, 'b' if source.suffix in ('.dll', '.pyd') else 'x'))
    if marker:
        marker_file = tmp_path / 'onefile.marker'
        marker_file.write_bytes(b'onefile fixture')
        entries.append(('onefile.marker', str(marker_file), True, 'x'))
    for name, source in (extras or {}).items():
        entries.append((name, str(source), True, 'b'))
    target = tmp_path / 'generated.exe'
    CArchiveWriter(str(target), entries, 'python312.dll')
    return target


def sidecar(executable, sources):
    internal = executable.parent / '_internal'
    internal.mkdir()
    for source in sources:
        (internal / source.name).write_bytes(source.read_bytes())


def test_onefile_hashes_real_embedded_bytes_and_detects_layout(tmp_path, sources):
    executable = archive(tmp_path, sources)
    assert smoke.tls_layout(executable) == 'onefile'
    assert smoke.verify_bundled_tls(executable) == [smoke.file_record(source) for source in sources]


def test_onefile_rejects_missing_tls_file(tmp_path, sources):
    executable = archive(tmp_path, sources, omitted=('libssl-3-x64.dll',))
    with pytest.raises(smoke.SmokeFailure, match='Required embedded TLS'):
        smoke.verify_bundled_tls(executable)


def test_onefile_cannot_use_valid_sidecar_to_hide_foreign_embedded_crypto(tmp_path, sources):
    executable = archive(tmp_path, sources, replacements={'libcrypto-3-x64.dll': b'foreign PHP OpenSSL'})
    sidecar(executable, sources)
    with pytest.raises(smoke.SmokeFailure, match='differs from build Python'):
        smoke.verify_bundled_tls(executable, 'onefile')


def test_onefile_rejects_missing_marker(tmp_path, sources):
    executable = archive(tmp_path, sources, marker=False)
    with pytest.raises(smoke.SmokeFailure, match='marked onefile'):
        smoke.verify_bundled_tls(executable)


def test_onefile_rejects_second_tls_copy(tmp_path, sources):
    executable = archive(tmp_path, sources, extras={'foreign/libcrypto-3-x64.dll': sources[1]})
    with pytest.raises(smoke.SmokeFailure, match='ambiguous copies'):
        smoke.verify_bundled_tls(executable)


def test_onedir_keeps_existing_contract_without_importing_pyinstaller(tmp_path, sources, monkeypatch):
    executable = tmp_path / 'EoingPDF.exe'
    executable.write_bytes(b'MZ fixture')
    sidecar(executable, sources)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith('PyInstaller'):
            raise AssertionError('onedir must not require archive inspection')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    assert smoke.tls_layout(executable) == 'onedir'
    assert smoke.verify_bundled_tls(executable) == [smoke.file_record(source) for source in sources]


def test_onedir_rejects_foreign_sidecar_crypto(tmp_path, sources):
    executable = tmp_path / 'EoingPDF.exe'
    executable.write_bytes(b'MZ fixture')
    sidecar(executable, sources)
    (executable.parent / '_internal/libcrypto-3-x64.dll').write_bytes(b'foreign PHP OpenSSL')
    with pytest.raises(smoke.SmokeFailure, match='differs from build Python'):
        smoke.verify_bundled_tls(executable)
