"""Per-user COM drop target registration. Explorer stays free of our code."""
from .localization import tr
from pathlib import Path
import ctypes
import winreg
import json
import os
from datetime import datetime

IDS = {
    'merge': '{7EA027AD-393A-49DE-9F95-7DA2CB0D9481}',
    'convert': '{7EA027AD-393A-49DE-9F95-7DA2CB0D9482}',
    'summary': '{7EA027AD-393A-49DE-9F95-7DA2CB0D9483}',
}
LABELS = {'merge': '어잉PDF · 하나로 합치기', 'convert': '어잉PDF · PDF로 변환', 'summary': '어잉PDF · 핵심문장 요약'}
BASE = r'Software\Classes\*\shell'
LEGACY_NAMES = ('EoingPDFMerge', 'EoingPDFConvert', 'EoingPDFCompress', 'EoingPDFOcr',
                'EoingPDFAiSummary', 'EoingPDFOpen', 'EoingPDFSplit10',
                'EoingPDFCompress5', 'EoingPDFImagesToPDF')


def set_value(path, name, value):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def install():
    from .distribution import shell_layout
    layout = shell_layout(prepare=True)
    bridge, exe, document_icon = layout.bridge, layout.executable, layout.icon
    if not bridge.is_file() or not exe.is_file():
        raise ValueError(tr('배포 폴더에 EoingPDF.exe와 EoingPDF.Shell.exe가 함께 있어야 합니다.'))
    if not document_icon.is_file():
        raise ValueError(tr('배포 폴더에 PDF 문서 아이콘이 없습니다. 전체 배포 폴더를 다시 풀어 주세요.'))
    for action, clsid in IDS.items():
        set_value('Software\\Classes\\CLSID\\' + clsid, '', tr(LABELS[action]))
        set_value('Software\\Classes\\CLSID\\' + clsid + r'\LocalServer32', '', layout.command(action))
        set_value('Software\\Classes\\CLSID\\' + clsid + r'\LocalServer32', 'ServerExecutable', str(bridge))
        key = BASE + '\\EoingPDF2.' + action
        set_value(key, '', tr(LABELS[action]))
        set_value(key, 'Icon', f'"{exe}",0')
        set_value(key, 'MultiSelectModel', 'Player')
        set_value(key + r'\DropTarget', 'CLSID', clsid)
    remove_legacy_menus()
    application = r'Software\Classes\Applications\EoingPDF.exe'
    set_value(application, 'FriendlyAppName', tr('어잉PDF'))
    set_value(application + r'\SupportedTypes', '.pdf', '')
    set_value(application + r'\shell\open\command', '', f'"{exe}" "%1"')
    progid = r'Software\Classes\EoingPDF.Document'
    set_value(progid, '', tr('어잉PDF 문서'))
    set_value(progid + r'\DefaultIcon', '', f'"{document_icon}",0')
    set_value(progid + r'\shell\open\command', '', f'"{exe}" "%1"')
    capabilities = r'Software\EoingPDF\Capabilities'
    set_value(capabilities, 'ApplicationName', tr('어잉PDF'))
    set_value(capabilities, 'ApplicationDescription', tr('PDF 보기, 페이지 삭제, 문서 변환과 병합'))
    set_value(capabilities + r'\FileAssociations', '.pdf', 'EoingPDF.Document')
    set_value(r'Software\RegisteredApplications', 'EoingPDF', capabilities)
    set_value(r'Software\Classes\.pdf\OpenWithProgids', 'EoingPDF.Document', '')
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def registration_status(folder=None):
    """Read-only check of the per-user registration owned by this install."""
    from .distribution import shell_layout
    layout = shell_layout(folder)
    exe, folder = layout.executable, layout.executable.parent
    expected = f'"{exe}" "%1"'
    result = {'folder': str(folder), 'pdf_open': False, 'actions': {}, 'owner': '없음', 'ready': False}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\EoingPDF.Document\shell\open\command') as key:
            command = winreg.QueryValueEx(key, '')[0]
        result['pdf_open'] = command.casefold() == expected.casefold()
        if command.casefold() != expected.casefold():
            result['owner'] = command
    except (FileNotFoundError, OSError):
        pass
    for action, clsid in IDS.items():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Classes\\CLSID\\' + clsid + r'\LocalServer32') as key:
                command = winreg.QueryValueEx(key, '')[0]
            result['actions'][action] = command.casefold() == layout.command(action).casefold()
        except (FileNotFoundError, OSError):
            result['actions'][action] = False
    result['ready'] = result['pdf_open'] and all(result['actions'].values())
    if result['ready']:
        result['owner'] = '현재 설치본'
    return result


def delete_owned_tree(path):
    # Only the fixed EoingPDF keys constructed here may be removed.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            children = []
            i = 0
            while True:
                try:
                    children.append(winreg.EnumKey(key, i))
                    i += 1
                except OSError:
                    break
        for child in children:
            delete_owned_tree(path + '\\' + child)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


def uninstall():
    from .distribution import shell_layout, cleanup_portable_shell
    expected = f'"{shell_layout().executable}" "%1"'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\EoingPDF.Document\shell\open\command') as key:
            registered = winreg.QueryValueEx(key, '')[0]
        if registered.casefold() != expected.casefold():
            return  # A newer install or portable copy owns the shared registration.
    except FileNotFoundError:
        pass
    delete_owned_tree(r'Software\Classes\Applications\EoingPDF.exe')
    delete_owned_tree(r'Software\Classes\EoingPDF.Document')
    delete_owned_tree(r'Software\EoingPDF\Capabilities')
    for path, name in [(r'Software\RegisteredApplications', 'EoingPDF'),
                       (r'Software\Classes\.pdf\OpenWithProgids', 'EoingPDF.Document')]:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
    for action, clsid in IDS.items():
        delete_owned_tree(BASE + '\\EoingPDF2.' + action)
        delete_owned_tree('Software\\Classes\\CLSID\\' + clsid)
    remove_legacy_menus()
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    cleanup_portable_shell()


def open_default_settings():
    # Windows owns UserChoice; ask the user through the documented Settings UI.
    os.startfile('ms-settings:defaultapps?registeredAppUser=EoingPDF')


def snapshot_key(path):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
        subkeys, values, _ = winreg.QueryInfoKey(key)
        data = [winreg.EnumValue(key, i) for i in range(values)]
        children = {winreg.EnumKey(key, i): snapshot_key(path + '\\' + winreg.EnumKey(key, i)) for i in range(subkeys)}
        return {'values': data, 'children': children}


def remove_legacy_menus():
    """Remove only the v1 keys whose names came from the previous project."""
    from .convert import SUPPORTED
    snapshots = {}
    for ext in sorted(SUPPORTED | {'.odt', '.ods', '.odp', '.xps', '.oxps'}):
        for name in LEGACY_NAMES:
            path = rf'Software\Classes\SystemFileAssociations\{ext}\shell\{name}'
            try:
                snapshots[path] = snapshot_key(path)
            except FileNotFoundError:
                continue
    if snapshots:
        backup = Path(os.environ['LOCALAPPDATA']) / 'EoingPDF/backups'
        backup.mkdir(parents=True, exist_ok=True)
        target = backup / ('legacy-menu-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        target.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2), encoding='utf-8')
        for path in snapshots:
            delete_owned_tree(path)
