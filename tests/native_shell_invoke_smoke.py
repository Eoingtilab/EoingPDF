"""Real native selection launch/queue consumption, without shell registration.

Creates only synthetic PDFs and one owned queue manifest per Invoke. The sibling
EXE records launch arguments; the real Python queue parser/jobs consume them.
This is not evidence of Explorer menu visibility or licensed GUI startup.
"""
import ctypes as C
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.quick import read_manifest
from eoingpdf.jobs import execute
from test_explorer_command import GUID, method, release


RECORDER = r'''
using System;
using System.IO;
using System.Text;
class Recorder {
    static int Main(string[] args) {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        File.WriteAllLines(Path.Combine(root, "receipt.txt"), args, new UTF8Encoding(false));
        File.WriteAllText(Path.Combine(root, "receipt.ready"), "ready");
        return 0;
    }
}
'''
HARNESS = r'''
using System;
using System.Windows.Forms;
class Harness {
    [STAThread] static int Main(string[] args) {
        DropTarget.Action = args[0];
        DropTarget.Executable = args[1];
        var paths = new string[args.Length - 2];
        Array.Copy(args, 2, paths, 0, paths.Length);
        var data = new DataObject(DataFormats.FileDrop, paths);
        uint effect = 1;
        return new DropTarget().Drop((System.Runtime.InteropServices.ComTypes.IDataObject)data, 0, 0, ref effect);
    }
}
'''


def compile_cs(folder, name, source, references=()):
    path = folder / (name + '.cs')
    path.write_text(source, encoding='utf-8-sig')
    target = folder / (name + '.exe')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    command = [str(compiler), '/nologo', '/target:winexe', '/platform:x64', '/out:' + str(target),
               '/reference:System.Windows.Forms.dll', *('/reference:' + str(p) for p in references), str(path)]
    result = subprocess.run(command, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def invoke_modern(dll_path, action_number, paths):
    dll = C.WinDLL(str(dll_path))
    ole, shell = C.OleDLL('ole32'), C.WinDLL('shell32')
    ole.CoInitializeEx(None, 2)
    ole.CoTaskMemFree.argtypes = [C.c_void_p]
    factory, command, selection = C.c_void_p(), C.c_void_p(), C.c_void_p()
    pidls = []
    try:
        get = dll.DllGetClassObject
        get.argtypes = [C.POINTER(GUID), C.POINTER(GUID), C.POINTER(C.c_void_p)]
        get.restype = C.c_long
        clsid = GUID(f'71bc7f3a-9d38-4ad1-b76c-9b3e1ea4500{action_number}')
        assert get(C.byref(clsid), C.byref(GUID('00000001-0000-0000-c000-000000000046')), C.byref(factory)) == 0
        create = method(factory, 3, C.c_long, C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_void_p))
        assert create(factory, None, C.byref(GUID('a08ce4d0-fa25-44ab-b57c-c7b1c323e0b9')), C.byref(command)) == 0
        parse = shell.SHParseDisplayName
        parse.argtypes = [C.c_wchar_p, C.c_void_p, C.POINTER(C.c_void_p), C.c_uint, C.c_void_p]
        parse.restype = C.c_long
        for path in paths:
            pidl = C.c_void_p()
            assert parse(str(path), None, C.byref(pidl), 0, None) == 0
            pidls.append(pidl)
        array = shell.SHCreateShellItemArrayFromIDLists
        array.argtypes = [C.c_uint, C.POINTER(C.c_void_p), C.POINTER(C.c_void_p)]
        array.restype = C.c_long
        assert array(len(pidls), (C.c_void_p * len(pidls))(*(p.value for p in pidls)), C.byref(selection)) == 0
        assert method(command, 8, C.c_long, C.c_void_p, C.c_void_p)(command, selection, None) == 0
    finally:
        release(selection)
        release(command)
        release(factory)
        for pidl in pidls:
            ole.CoTaskMemFree(pidl)
        assert dll.DllCanUnloadNow() == 0
        ole.CoUninitialize()
        kernel = C.WinDLL('kernel32')
        kernel.FreeLibrary.argtypes = [C.c_void_p]
        kernel.FreeLibrary(dll._handle)


def consume_receipt(folder, action, paths, output):
    ready = folder / 'receipt.ready'
    deadline = time.monotonic() + 10
    while not ready.exists():
        assert time.monotonic() < deadline, 'Native receiver did not start'
        time.sleep(.025)
    args = (folder / 'receipt.txt').read_text(encoding='utf-8').splitlines()
    assert args[:3] == ['--quick', action, '--manifest'], args
    manifest = Path(os.path.abspath(args[3]))
    queue = Path(os.path.abspath(Path(os.environ['LOCALAPPDATA']) / 'EoingPDF/queue'))
    assert manifest.parent == queue and manifest.suffix == '.files', (str(manifest), str(queue), args)
    try:
        consumed = read_manifest(manifest)
        assert consumed == [str(p.resolve()) for p in paths]
        result = execute(action, consumed, output)
        assert not result['errors'] and not result['cancelled'], result
        assert len(result['outputs']) == (1 if action == 'merge' else len(paths))
        if action == 'merge':
            with pdf.open(result['outputs'][0]) as document:
                assert len(document) == len(paths)
                for index, page in enumerate(document):
                    assert f'SYNTHETIC {index}' in page.get_text()
        return len(result['outputs'])
    finally:
        manifest.unlink(missing_ok=True)  # only the exact manifest from this launch
        assert not manifest.exists()


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='native-shell-invoke-', dir=ROOT / 'temp') as temporary:
        folder = Path(temporary).resolve()
        assert folder.is_relative_to((ROOT / 'temp').resolve())
        executable = compile_cs(folder, 'EoingPDF', RECORDER)
        renamed = folder / '어잉 portable copy.exe'
        shutil.copyfile(executable, renamed)
        bridge = compile_cs(folder, 'EoingPDF.Shell', (ROOT / 'native/ShellBridge.cs').read_text(encoding='utf-8'))
        harness = compile_cs(folder, 'Harness', HARNESS, [bridge])
        dll = folder / 'EoingPDF.Explorer.dll'
        shutil.copyfile(ROOT / 'assets/EoingPDF.Explorer.dll', dll)
        paths = [folder / name for name in ('첫 문서.pdf', '日本語 & space.pdf', 'third.pdf')]
        for index, path in enumerate(paths):
            with pdf.open() as doc:
                doc.new_page().insert_text((40, 60), f'SYNTHETIC {index}. This is an offline selection test.')
                doc.save(path)
        originals = [p.read_bytes() for p in paths]
        for provider in ('classic', 'modern'):
            for number, action in enumerate(('merge', 'convert', 'summary'), 1):
                (folder / 'receipt.ready').unlink(missing_ok=True)
                if provider == 'classic':
                    result = subprocess.run([str(harness), action, str(renamed), *map(str, paths)],
                        capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
                    assert result.returncode == 0, (result.returncode, result.stderr)
                else:
                    invoke_modern(dll, number, paths)
                count = consume_receipt(folder, action, paths, folder / 'outputs' / provider / action)
                results.append({'provider': provider, 'action': action, 'selected': 3, 'outputs': count})
                assert [p.read_bytes() for p in paths] == originals
                print(f'PASS {provider} {action}: native launch, Unicode selection order, real queue parser/jobs, original preservation', flush=True)
        # Allow the very short receiver process to release its executable image.
        time.sleep(.2)
    (ROOT / 'temp/native-shell-invoke-report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
