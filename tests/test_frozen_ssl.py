"""Build-only regression tests for Python/PHP OpenSSL DLL name collisions."""
import importlib.util
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('frozen_ssl', ROOT / 'packaging/frozen_ssl.py')
frozen_ssl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen_ssl)


@pytest.fixture
def python_dlls(tmp_path):
    directory = tmp_path / 'python' / 'DLLs'
    directory.mkdir(parents=True)
    extension = directory / '_ssl.pyd'
    extension.write_bytes(b'fixture extension')
    for name in frozen_ssl.SSL_DLL_NAMES:
        (directory / name).write_bytes(b'fixture Python DLL')
    return extension


def test_analysis_inputs_are_from_the_ssl_extension_directory(python_dlls):
    binaries = frozen_ssl.python_ssl_binaries(python_dlls)
    assert binaries == [(str(python_dlls.parent / name), '.')
                        for name in frozen_ssl.SSL_DLL_NAMES]


def test_uses_build_interpreter_extension_without_path_search(monkeypatch, python_dlls):
    class Module:
        origin = str(python_dlls)

    monkeypatch.setattr(frozen_ssl, 'find_spec', lambda name: Module() if name == '_ssl' else None)
    monkeypatch.setenv('PATH', str(python_dlls.parent.parent / 'PHP'))
    assert frozen_ssl.python_ssl_binaries() == frozen_ssl.python_ssl_binaries(python_dlls)


@pytest.mark.parametrize('name', frozen_ssl.SSL_DLL_NAMES)
def test_missing_python_dll_fails_instead_of_falling_back_to_path(monkeypatch, python_dlls, name):
    (python_dlls.parent / name).unlink()
    foreign = python_dlls.parent.parent / 'PHP'
    foreign.mkdir()
    (foreign / name).write_bytes(b'foreign PHP DLL')
    monkeypatch.setenv('PATH', str(foreign))
    with pytest.raises(FileNotFoundError):
        frozen_ssl.python_ssl_binaries(python_dlls)


def test_missing_ssl_module_fails_closed(monkeypatch):
    monkeypatch.setattr(frozen_ssl, 'find_spec', lambda name: None)
    with pytest.raises(RuntimeError, match='does not provide _ssl'):
        frozen_ssl.python_ssl_binaries()


def test_final_toc_replaces_php_dlls_and_preserves_unrelated_entries(python_dlls):
    unrelated = [('Qt6Core.dll', 'Qt/Qt6Core.dll', 'BINARY'),
                 ('_ssl.pyd', str(python_dlls), 'EXTENSION'),
                 ('other/data.bin', 'some/data.bin', 'DATA')]
    original = [('libssl-3-x64.dll', 'PHP/libssl-3-x64.dll', 'BINARY'),
                unrelated[0],
                ('nested\\LIBCRYPTO-3-X64.DLL', 'PHP/libcrypto-3-x64.dll', 'BINARY'),
                unrelated[1], unrelated[2],
                ('duplicate/libssl-3-x64.dll', 'PHP/libssl-3-x64.dll', 'BINARY')]
    unchanged = list(original)
    binaries = frozen_ssl.python_ssl_binaries(python_dlls)
    result = frozen_ssl.pin_ssl_binaries(original, binaries)
    assert result == unrelated + [(name, str(python_dlls.parent / name), 'BINARY')
                                  for name in frozen_ssl.SSL_DLL_NAMES]
    assert original == unchanged


def test_final_toc_adds_pair_if_analysis_omits_it(python_dlls):
    result = frozen_ssl.pin_ssl_binaries([], frozen_ssl.python_ssl_binaries(python_dlls))
    assert {entry[0] for entry in result} == set(frozen_ssl.SSL_DLL_NAMES)


def test_final_toc_rechecks_canonical_files(python_dlls):
    binaries = frozen_ssl.python_ssl_binaries(python_dlls)
    (python_dlls.parent / frozen_ssl.SSL_DLL_NAMES[0]).unlink()
    with pytest.raises(FileNotFoundError):
        frozen_ssl.pin_ssl_binaries([], binaries)


def test_final_toc_rejects_incomplete_pair(python_dlls):
    with pytest.raises(RuntimeError, match='Both Python OpenSSL'):
        frozen_ssl.pin_ssl_binaries([], frozen_ssl.python_ssl_binaries(python_dlls)[:1])


def test_final_toc_rejects_pair_from_different_directories(tmp_path, python_dlls):
    binaries = frozen_ssl.python_ssl_binaries(python_dlls)
    other = tmp_path / frozen_ssl.SSL_DLL_NAMES[1]
    other.write_bytes(b'foreign DLL')
    with pytest.raises(RuntimeError, match='one directory'):
        frozen_ssl.pin_ssl_binaries([], [binaries[0], (str(other), '.')])


def test_referenced_ssl_policy_is_included_without_rewriting(tmp_path):
    source = tmp_path / 'ssl.py'
    source.write_text("cafile = os.path.join(os.path.dirname(__file__), 'codex-rejected-cas.pem')")
    policy = tmp_path / frozen_ssl.SSL_POLICY_FILE
    original = b'-----BEGIN TRUSTED CERTIFICATE-----\nfixture rejection policy\n'
    policy.write_bytes(original)
    assert frozen_ssl.python_ssl_data(source) == [(str(policy), '.')]
    assert policy.read_bytes() == original


def test_referenced_ssl_policy_missing_fails_closed(tmp_path):
    source = tmp_path / 'ssl.py'
    source.write_text("cafile = 'codex-rejected-cas.pem'")
    with pytest.raises(FileNotFoundError):
        frozen_ssl.python_ssl_data(source)


@pytest.mark.parametrize('unreferenced_policy_present', [False, True])
def test_ordinary_cpython_needs_no_extra_ssl_data(tmp_path, unreferenced_policy_present):
    source = tmp_path / 'ssl.py'
    source.write_text('class SSLContext: pass\n')
    if unreferenced_policy_present:
        (tmp_path / frozen_ssl.SSL_POLICY_FILE).write_bytes(b'unreferenced')
    assert frozen_ssl.python_ssl_data(source) == []


def test_spec_includes_selected_ssl_data_in_analysis(monkeypatch):
    # Exercise the spec's integration with synthetic build objects. No binary
    # collection or app build runs, and no installed runtime files are changed.
    hooks = ModuleType('PyInstaller.utils.hooks')
    hooks.collect_data_files = lambda package: []
    hooks.copy_metadata = lambda package: []
    monkeypatch.setitem(sys.modules, 'PyInstaller.utils.hooks', hooks)
    ssl_inputs = [('fixture/python/libssl-3-x64.dll', '.')]
    policy_input = [('fixture/python/codex-rejected-cas.pem', '.')]
    monkeypatch.setattr(runpy, 'run_path', lambda path: {
        'python_ssl_binaries': lambda: ssl_inputs,
        'python_ssl_data': lambda: policy_input,
        'pin_ssl_binaries': lambda entries, binaries: entries,
    })
    monkeypatch.setenv('EOINGPDF_BUILD_ONEFILE', '0')
    captured = {}

    def analysis(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(binaries=[], datas=[], pure=[], scripts=[])

    exec(compile((ROOT / 'packaging/EoingPDF.spec').read_text(encoding='utf-8'),
                 'EoingPDF.spec', 'exec'), {
                     'SPECPATH': str(ROOT / 'packaging'),
                     'Analysis': analysis,
                     'PYZ': lambda entries: None,
                     'EXE': lambda *args, **kwargs: None,
                     'COLLECT': lambda *args, **kwargs: None,
                 })
    assert captured['binaries'] == ssl_inputs
    assert policy_input[0] in captured['datas']
