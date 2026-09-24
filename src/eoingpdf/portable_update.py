"""Replace only the owned portable EXE, with verified backup and atomic publication."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

from .localization import tr, current_locale
from .update_snapshot import digest


def safe_path(value):
    path = Path(os.path.abspath(value))
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(tr('연결된 파일은 업데이트 백업에서 지원하지 않습니다.'))
    return path


def backup_root():
    return safe_path(Path(os.environ['LOCALAPPDATA']) / 'EoingPDF/updates/portable-backups')


def create(executable, folder, version):
    from .updates import verify_installer, version_tuple
    executable, folder = safe_path(executable), safe_path(folder)
    version_tuple(version)
    expected = digest(executable)
    verify_installer(executable, expected)
    folder.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='portable-', dir=folder))
    # A failed copy remains unlisted until a complete manifest exists.
    shutil.copy2(executable, backup / 'EoingPDF.exe')
    verify_installer(backup / 'EoingPDF.exe', expected)
    if digest(executable) != expected:
        raise ValueError(tr('백업 중 설치 파일이 변경되었습니다.'))
    manifest = dict(schema=1, kind='onefile', source=str(executable), version=version, sha256=expected)
    (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    validate(backup, executable)
    return backup


def validate(backup, executable):
    from .updates import verify_installer, version_tuple
    backup, executable = safe_path(backup), safe_path(executable)
    with safe_path(backup / 'manifest.json').open('rb') as stream:
        payload = stream.read(8193)
    if len(payload) > 8192:
        raise ValueError(tr('백업 파일 정보가 올바르지 않습니다.'))
    manifest = json.loads(payload)
    if (not isinstance(manifest, dict) or manifest.get('schema') != 1
            or manifest.get('kind') != 'onefile' or manifest.get('source') != str(executable)
            or executable.suffix.lower() != '.exe' or executable == backup / 'EoingPDF.exe'):
        raise ValueError(tr('현재 실행 파일의 포터블 백업이 아닙니다.'))
    version_tuple(manifest.get('version'))
    verify_installer(safe_path(backup / 'EoingPDF.exe'), manifest.get('sha256'))
    return manifest


def latest(executable=None):
    executable = safe_path(executable or sys.executable)
    folder = backup_root()
    candidates = []
    for item in folder.glob('portable-*') if folder.is_dir() else ():
        try:
            safe_path(item)
            candidates.append((item.stat().st_mtime_ns, item))
        except (OSError, ValueError):
            continue
    for _, item in sorted(candidates, reverse=True):
        try:
            manifest = validate(item, executable)
            return item, manifest['version']
        except (OSError, ValueError, TypeError):
            continue
    return None


def replace_file(source, executable, expected, current_digest):
    """A single same-volume rename never leaves a missing/partially copied EXE."""
    from .updates import verify_installer
    source, executable = safe_path(source), safe_path(executable)
    verify_installer(source, expected)
    fd, name = tempfile.mkstemp(prefix='.eoing-update-', suffix='.exe', dir=executable.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as original:
            shutil.copyfileobj(original, output)
            output.flush()
            os.fsync(output.fileno())
        verify_installer(staged, expected)
        deadline = time.monotonic() + 20
        while True:
            safe_path(executable)
            if digest(executable) != current_digest:
                raise ValueError(tr('실행 파일이 변경되어 자동 교체를 중단했습니다.'))
            try:
                os.replace(staged, executable)
                break
            except PermissionError:
                # The onefile bootloader may retain the EXE briefly after Python exits.
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
    finally:
        staged.unlink(missing_ok=True)
    return executable


def runtime_healthy(executable, version):
    with tempfile.TemporaryDirectory(prefix='portable-health-') as folder:
        report, nonce = Path(folder) / 'result.json', secrets.token_hex(16)
        try:
            process = subprocess.Popen([str(executable), '--health-check', str(report), nonce, version, 'onefile'],
                cwd=executable.parent, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
                env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
        except OSError:
            return False
        # A timeout propagates: never restore while a probe might still own the EXE.
        code = process.wait(timeout=60)
        try:
            return (code == 0 and report.stat().st_size <= 4096
                    and json.loads(report.read_text(encoding='utf-8')) == {'ok': True, 'nonce': nonce})
        except (OSError, ValueError):
            return False


def apply(packet):
    from .update_helper import write_status
    from .updates import verify_installer, version_tuple
    target, backup = safe_path(packet['executable']), safe_path(packet['backup'])
    manifest = validate(backup, target)
    expected_current = packet['current_digest']
    verify_installer(target, expected_current)
    if not packet.get('installer'):
        write_status(packet['report'], 'restoring')
        replace_file(backup / 'EoingPDF.exe', target, manifest['sha256'], expected_current)
        return 'restored'
    candidate = safe_path(packet['installer'])
    if expected_current != manifest['sha256']:
        raise ValueError(tr('백업 중 설치 파일이 변경되었습니다.'))
    version_tuple(packet['version'])
    if version_tuple(packet['version']) <= version_tuple(manifest['version']):
        raise ValueError(tr('업데이트 버전은 현재 버전보다 높아야 합니다.'))
    verify_installer(candidate, packet['digest'])
    write_status(packet['report'], 'checking')
    if not runtime_healthy(candidate, packet['version']):
        raise ValueError(tr('새 포터블 실행 파일의 버전 또는 실행 검사에 실패했습니다.'))
    write_status(packet['report'], 'installing')
    replace_file(candidate, target, packet['digest'], expected_current)
    write_status(packet['report'], 'checking')
    if runtime_healthy(target, packet['version']):
        return 'updated'
    write_status(packet['report'], 'restoring')
    replace_file(backup / 'EoingPDF.exe', target, manifest['sha256'], packet['digest'])
    return 'restored'


def run(packet):
    from .update_helper import parent_handle, write_status
    kernel = handle = None
    report = packet['report']
    try:
        executable = safe_path(packet['executable'])
        validate(packet['backup'], executable)
        kernel, handle = parent_handle(packet['pid'])
        write_status(report, 'ready')
        deadline = time.monotonic() + 20
        while not Path(report).with_suffix('.go').is_file():
            if time.monotonic() >= deadline:
                raise OSError(tr('복구 시작 승인을 받지 못했습니다.'))
            time.sleep(.05)
        if kernel.WaitForSingleObject(handle, 120000) != 0:
            raise OSError(tr('앱이 종료되지 않아 복원을 시작하지 않았습니다.'))
        state = apply(packet)
        write_status(report, state)
        if packet.get('restart', True):
            subprocess.Popen([str(executable), '--skip-update-once'], cwd=executable.parent,
                creationflags=subprocess.CREATE_NO_WINDOW,
                env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
        return 0
    except Exception as error:
        write_status(report, 'failed', str(error))
        return 1
    finally:
        if handle:
            kernel.CloseHandle(handle)


def launch(backup, installer=None, expected=None, version=None):
    from .update_helper import read_status
    from .updates import verify_installer
    executable, backup = safe_path(sys.executable), safe_path(backup)
    validate(backup, executable)
    jobs = safe_path(Path(os.environ['LOCALAPPDATA']) / 'EoingPDF/updates/jobs')
    jobs.mkdir(parents=True, exist_ok=True)
    job = Path(tempfile.mkdtemp(prefix='portable-', dir=jobs))
    report = job / 'status.json'
    packet = dict(kind='onefile', backup=str(backup), executable=str(executable),
                  current_digest=digest(executable), pid=os.getpid(), report=str(report),
                  restart=True, locale=current_locale())
    if installer is not None:
        verify_installer(installer, expected)
        packet.update(installer=str(safe_path(installer)), digest=expected, version=version)
    process = subprocess.Popen([str(backup / 'EoingPDF.exe'), '--maintenance-child'],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=backup,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
    process.stdin.write(json.dumps(packet).encode('utf-8'))
    process.stdin.close()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = read_status(report)
        if state:
            if state['state'] == 'ready':
                report.with_suffix('.go').write_text('replace', encoding='ascii')
                return report
            if state['state'] == 'failed':
                raise OSError(state['message'])
        if process.poll() is not None:
            raise OSError(tr('복구 도우미를 시작하지 못했습니다. 현재 프로그램은 유지됩니다.'))
        time.sleep(.05)
    raise OSError(tr('복구 도우미 준비 시간이 초과되었습니다. 현재 프로그램은 유지됩니다.'))
