from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
onefile = os.environ.get('EOINGPDF_BUILD_ONEFILE') == '1'
extra_data = [(str(root / 'VERSION'), '.')]
if onefile:
    extra_data += [(str(root / 'packaging/onefile.marker'), '.'),
                   (str(root / 'build/portable-tools/EoingPDF.Shell.exe'), 'portable_tools')]
a = Analysis(
    [str(root / 'main.py')], pathex=[str(root / 'src')],
    binaries=[], datas=[(str(root / 'assets'), 'assets')] + extra_data + collect_data_files('onnxruntime')
        + copy_metadata('onnxruntime') + copy_metadata('tokenizers'),
    hiddenimports=['win32timezone'],
    excludes=['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore', 'tkinter', 'matplotlib'],
)
# Qt expects the Windows ICU API. A similarly named third-party ICU on PATH
# exports version-suffixed symbols and makes a frozen app fail at import.
# Windows 10/11 provides the required system DLL; never bundle a PATH copy.
allowed_qt = {'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'qt6network.dll'}
def needed(entry):
    name = Path(entry[0]).name.lower()
    if name == 'eoingpdf.explorer.dll':
        return False  # Built separately beside the application for COM activation.
    location = entry[0].replace('\\', '/').lower()
    if name.startswith(('icuuc', 'icuin', 'icudt')):
        return False
    if name.startswith('qt6') and name.endswith('.dll') and name not in allowed_qt:
        return False
    if '/plugins/' in location and name not in {'qwindows.dll', 'qoffscreen.dll'}:
        return False
    if name in {'opengl32sw.dll', '_avif.cp312-win_amd64.pyd'}:
        return False
    return True
a.binaries = [entry for entry in a.binaries if needed(entry)]
a.datas = [entry for entry in a.datas if Path(entry[0]).name.lower() != 'eoingpdf.explorer.dll']
pyz = PYZ(a.pure)
if onefile:
    version = (root / 'VERSION').read_text(encoding='utf-8-sig').strip()
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=f'EoingPDF-{version}-portable',
              console=False, upx=False, icon=str(root / 'assets/app_icon.ico'))
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='EoingPDF', console=False, upx=False, icon=str(root / 'assets/app_icon.ico'))
    coll = COLLECT(exe, a.binaries, a.datas, name='EoingPDF', upx=False)
