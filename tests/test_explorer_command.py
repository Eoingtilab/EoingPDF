"""Exercise the native COM ABI without registering a Shell extension."""
import ctypes as C
import json
from pathlib import Path
import shutil
import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows COM')


class GUID(C.Structure):
    _fields_ = [('bytes', C.c_ubyte * 16)]
    def __init__(self, value):
        super().__init__()
        self.bytes[:] = uuid.UUID(value).bytes_le


def method(pointer, index, result, *arguments):
    table = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(result, C.c_void_p, *arguments)(table[index])


def release(pointer):
    if pointer:
        method(pointer, 2, C.c_ulong)(pointer)


@pytest.mark.parametrize('action', [1, 2, 3])
def test_command_titles_selection_validation_and_unload(tmp_path, action):
    dll_path = tmp_path / 'EoingPDF.Explorer.dll'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'assets/EoingPDF.Explorer.dll', dll_path)
    dll = C.WinDLL(str(dll_path))
    ole = C.OleDLL('ole32')
    ole.CoInitializeEx(None, 2)
    ole.CoTaskMemFree.argtypes = [C.c_void_p]
    factory = command = C.c_void_p()
    items = []
    try:
        get = dll.DllGetClassObject
        get.argtypes = [C.POINTER(GUID), C.POINTER(GUID), C.POINTER(C.c_void_p)]
        get.restype = C.c_long
        dll.DllCanUnloadNow.restype = C.c_long
        assert dll.DllCanUnloadNow() == 0
        class_id = GUID(f'71bc7f3a-9d38-4ad1-b76c-9b3e1ea4500{action}')
        factory_id = GUID('00000001-0000-0000-c000-000000000046')
        factory = C.c_void_p()
        assert get(C.byref(class_id), C.byref(factory_id), C.byref(factory)) == 0
        create = method(factory, 3, C.c_long, C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_void_p))
        command_id = GUID('a08ce4d0-fa25-44ab-b57c-c7b1c323e0b9')
        command = C.c_void_p()
        assert create(factory, None, C.byref(command_id), C.byref(command)) == 0
        assert dll.DllCanUnloadNow() == 1
        title = C.c_void_p()
        assert method(command, 3, C.c_long, C.c_void_p, C.POINTER(C.c_void_p))(command, None, C.byref(title)) == 0
        try:
            primary = C.WinDLL('kernel32').GetUserDefaultUILanguage() & 0x3ff
            locale = {0x12: 'ko-KR', 0x09: 'en-US', 0x11: 'ja-JP'}.get(primary, 'ko-KR')
            catalog = json.loads((Path(__file__).resolve().parents[1] / 'assets/locales' / (locale + '.json')).read_text(encoding='utf-8'))
            key = ('어잉PDF · 하나로 합치기', '어잉PDF · PDF로 변환', '어잉PDF · 핵심문장 요약')[action - 1]
            assert C.wstring_at(title) == catalog[key]
        finally:
            ole.CoTaskMemFree(title)
        canonical = GUID('00000000-0000-0000-0000-000000000000')
        assert method(command, 6, C.c_long, C.POINTER(GUID))(command, C.byref(canonical)) == 0
        assert bytes(canonical.bytes) == bytes(class_id.bytes)

        shell = C.WinDLL('shell32')
        parse = shell.SHCreateItemFromParsingName
        parse.argtypes = [C.c_wchar_p, C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_void_p)]
        parse.restype = C.c_long
        array = shell.SHCreateShellItemArrayFromShellItem
        array.argtypes = [C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_void_p)]
        array.restype = C.c_long
        item_id = GUID('43826d1e-e718-42ee-bc55-a1e261c37bfe')
        array_id = GUID('b63ea76d-1f85-456f-a19c-48159efa858b')
        state_method = method(command, 7, C.c_long, C.c_void_p, C.c_int, C.POINTER(C.c_int))
        for name, folder, expected in [('한글 문서.pdf', False, 0), ('file.exe', False, 2), ('folder.pdf', True, 2)]:
            path = tmp_path / name
            path.mkdir() if folder else path.write_bytes(b'fixture')
            item, selection = C.c_void_p(), C.c_void_p()
            assert parse(str(path), None, C.byref(item_id), C.byref(item)) == 0
            try:
                assert array(item, C.byref(array_id), C.byref(selection)) == 0
            finally:
                release(item)
            items.append(selection)
            state = C.c_int()
            assert state_method(command, selection, 0, C.byref(state)) == C.c_long(0x8000000A).value
            assert state_method(command, selection, 1, C.byref(state)) == 0
            assert state.value == expected
        # Missing sibling app must fail, never resolve some other executable via PATH.
        assert method(command, 8, C.c_long, C.c_void_p, C.c_void_p)(command, items[0], None) == C.c_long(0x80070002).value
    finally:
        for value in items:
            release(value)
        release(command)
        release(factory)
        assert dll.DllCanUnloadNow() == 0
        ole.CoUninitialize()
        kernel = C.WinDLL('kernel32')
        kernel.FreeLibrary.argtypes = [C.c_void_p]
        kernel.FreeLibrary(dll._handle)
