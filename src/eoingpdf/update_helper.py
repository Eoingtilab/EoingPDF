"""Run snapshot restoration from an independent process after its parent exits."""
from .localization import tr, current_locale, configure_language
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import secrets
from .update_snapshot import validate, restore


def write_status(path, state, message=''):
    target = Path(path)
    # Readers and Windows scanners can briefly hold the previous file open.
    # Keep a complete old status until the new, closed file can be replaced.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                     prefix=target.name + '.', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump({'state': state, 'message': message}, stream, ensure_ascii=False)
    try:
        for attempt in range(21):
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if attempt == 20:
                    raise
                time.sleep(.05)
    finally:
        temporary.unlink(missing_ok=True)


def read_status(path):
    """A sharing violation is pending, never readiness or authorization."""
    try:
        with Path(path).open('rb') as stream:
            content = stream.read(65537)
    except (FileNotFoundError, PermissionError):
        return None
    if len(content) > 65536:
        raise ValueError(tr('복구 도우미 상태 파일이 너무 큽니다.'))
    state = json.loads(content)
    if (not isinstance(state, dict) or not isinstance(state.get('state'), str)
            or not isinstance(state.get('message', ''), str)):
        raise ValueError(tr('복구 도우미 상태 파일이 올바르지 않습니다.'))
    return state


def parent_handle(pid):
    if type(pid) is not int or pid <= 0 or pid == os.getpid():
        raise ValueError(tr('종료를 기다릴 프로그램 정보가 올바르지 않습니다.'))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        raise OSError(tr('앱의 종료 대기 핸들을 열 수 없습니다.'))
    return kernel, handle


def install_update(packet, install, backup):
    from .updates import verify_installer, version_tuple
    installer = Path(packet['installer']).resolve()
    verify_installer(installer, packet['digest'])
    write_status(packet['report'], 'installing')
    process = subprocess.Popen([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                                '/AUTOUPDATE=1', '/HELPERMANAGED=1', f'/DIR={install}'],
                               creationflags=subprocess.CREATE_NO_WINDOW)
    # On timeout the installer may still own files. Never restore concurrently.
    code = process.wait(timeout=900)
    valid = code == 0
    if valid:
        try:
            installed_version = version_tuple((install / 'VERSION').read_text(encoding='utf-8-sig').strip())
            if packet.get('version') and installed_version != version_tuple(packet['version']):
                raise ValueError(tr('설치된 버전이 업데이트 대상과 다릅니다.'))
            with (install / 'EoingPDF.exe').open('rb') as executable:
                valid = executable.read(2) == b'MZ'
        except (OSError, ValueError):
            valid = False
    if valid:
        write_status(packet['report'], 'checking')
        valid = runtime_healthy(install)
    if valid:
        return 'updated'
    write_status(packet['report'], 'restoring', tr('설치 종료 코드: {v0}', v0=code))
    restore(backup, install)
    return 'restored'


def runtime_healthy(install):
    """Probe the newly installed process and release its files before rollback."""
    with tempfile.TemporaryDirectory(prefix='eoing-health-result-') as folder:
        report = Path(folder) / 'result.json'
        nonce = secrets.token_hex(16)
        try:
            process = subprocess.Popen([str(install / 'EoingPDF.exe'), '--health-check', str(report), nonce],
                cwd=install, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            return False
        try:
            code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            # Only our dedicated probe is terminated. If it cannot exit, propagate
            # rather than restore DLLs that may still be loaded by that process.
            process.kill()
            process.wait(timeout=5)
            return False
        try:
            if code != 0 or report.stat().st_size > 4096:
                return False
            return json.loads(report.read_text(encoding='utf-8')) == {'ok': True, 'nonce': nonce}
        except (OSError, ValueError):
            return False


def run(packet):
    if packet.get('kind') == 'onefile':
        from .portable_update import run as run_portable
        return run_portable(packet)
    report = packet['report']
    kernel = handle = None
    try:
        install, backup = Path(packet['install']).resolve(), Path(packet['backup']).resolve()
        if backup.is_relative_to(install):
            raise ValueError(tr('복구 도우미의 백업은 설치 폴더 밖에 있어야 합니다.'))
        validate(backup, install)
        kernel, handle = parent_handle(packet['pid'])
        write_status(report, 'ready')
        authorization = Path(report).with_suffix('.go')
        deadline = time.monotonic() + 20
        while not authorization.is_file():
            if time.monotonic() >= deadline:
                raise OSError(tr('복구 시작 승인을 받지 못했습니다.'))
            time.sleep(.05)
        result = kernel.WaitForSingleObject(handle, 120000)
        if result != 0:
            raise OSError(tr('앱이 종료되지 않아 복원을 시작하지 않았습니다.'))
        if packet.get('installer'):
            state = install_update(packet, install, backup)
        else:
            write_status(report, 'restoring')
            restore(backup, install)
            state = 'restored'
        restored = install / 'EoingPDF.exe'
        write_status(report, state)
        if packet.get('restart', True):
            subprocess.Popen([str(restored)] + (['--skip-update-once'] if state == 'restored' else []),
                             cwd=install, creationflags=subprocess.CREATE_NO_WINDOW)
        return 0
    except Exception as error:
        write_status(report, 'failed', str(error))
        return 1
    finally:
        if handle:
            kernel.CloseHandle(handle)


def child_main():
    try:
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            return 2
        packet = json.loads(payload)
        configure_language(packet.get('locale'))
        return run(packet)
    except Exception:
        return 2


def launch(backup, install=None, installer=None, digest=None, version=None):
    if not getattr(sys, 'frozen', False):
        raise ValueError(tr('설치형 또는 포터블 실행본에서 복원할 수 있습니다.'))
    from .distribution import is_onefile
    if is_onefile():
        from .portable_update import launch as launch_portable
        return launch_portable(backup, installer, digest, version)
    install = Path(install or Path(sys.executable).parent).resolve()
    backup = Path(backup).resolve()
    validate(backup, install)
    if backup.is_relative_to(install):
        raise ValueError(tr('설치 폴더 밖의 백업이 필요합니다.'))
    jobs = Path(os.environ['LOCALAPPDATA']) / 'EoingPDF' / 'updates' / 'jobs'
    jobs.mkdir(parents=True, exist_ok=True)
    job = Path(tempfile.mkdtemp(prefix='restore-', dir=jobs))
    report = job / 'status.json'
    packet = dict(backup=str(backup), install=str(install), report=str(report), pid=os.getpid(),
                  restart=True, locale=current_locale())
    if installer is not None:
        from .updates import verify_installer
        verify_installer(installer, digest)
        packet.update(installer=str(Path(installer).resolve()), digest=digest, version=version)
    process = subprocess.Popen([str(backup / 'EoingPDF.exe'), '--maintenance-child'],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               cwd=backup, creationflags=subprocess.CREATE_NO_WINDOW)
    process.stdin.write(json.dumps(packet).encode('utf-8'))
    process.stdin.close()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = read_status(report)
        if state is not None:
            if state['state'] == 'ready':
                report.with_suffix('.go').write_text('restore', encoding='ascii')
                return report
            if state['state'] == 'failed':
                raise OSError(state['message'])
        if process.poll() is not None:
            raise OSError(tr('복구 도우미를 시작하지 못했습니다. 현재 프로그램은 유지됩니다.'))
        time.sleep(.05)
    raise OSError(tr('복구 도우미 준비 시간이 초과되었습니다. 현재 프로그램은 유지됩니다.'))
