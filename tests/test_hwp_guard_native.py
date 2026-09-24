import ctypes
from ctypes import wintypes
from pathlib import Path
import shutil
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows native callback')
def test_native_callback_exact_paths_and_revocation(tmp_path):
    source = ROOT / 'assets/hwp-x64.dll'
    if not source.is_file():
        pytest.skip('Build native HWP guard first')
    module = tmp_path / 'guard.dll'
    shutil.copyfile(source, module)
    library = ctypes.WinDLL(str(module))
    callback = library.IsAccessiblePath
    callback.argtypes = [wintypes.HWND, wintypes.LONG, wintypes.LPCWSTR, wintypes.LPCWSTR]
    callback.restype = wintypes.BOOL
    allowed = tmp_path / 'allowed.txt'
    document = tmp_path / 'document.hwp'
    output = tmp_path / 'document.pdf'
    try:
        assert not callback(None, 0, str(document), None)
        allowed.write_text(f'{document}\n{output}\n', encoding='utf-16-le')
        assert callback(None, 0, str(document), None)
        assert callback(None, 0, str(output), None)
        assert not callback(None, 0, str(tmp_path / 'other.pdf'), None)
        assert not callback(None, 0, None, None)
        assert not callback(None, 0, '', None)
        assert not callback(None, 0, 'C:\\' + 'a' * 40000, None)
        for content in (b'', b'x', b'\0' * 131074):
            allowed.write_bytes(content)
            assert not callback(None, 0, str(document), None)
        allowed.unlink()
        assert not callback(None, 0, str(document), None)
    finally:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.FreeLibrary.argtypes = [wintypes.HMODULE]
        kernel.FreeLibrary.restype = wintypes.BOOL
        assert kernel.FreeLibrary(library._handle)
