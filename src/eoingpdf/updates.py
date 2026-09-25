"""EDD updates: check and download off the UI thread, install only when idle."""
from .localization import tr
import hashlib
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from urllib.error import URLError
from .licensing import store, LicenseError


UPDATE_PRODUCT_ID = 'eoingpdf'
UPDATE_MANIFEST_URL = (
    'https://raw.githubusercontent.com/Eoingtilab/nalapps-releases/'
    'main/products/eoingpdf/latest.json'
)
UPDATE_RELEASE_REPO = 'Eoingtilab/nalapps-releases'
UPDATE_RELEASE_TAG_PREFIX = 'utility-eoingpdf-v'
UPDATE_MANIFEST_MAX_BYTES = 64 * 1024
UPDATE_ASSET_MAX_BYTES = 200 * 1024 * 1024



def backup_current_install(install_dir=None):
    """Keep a verified snapshot of the packaged application before an update starts."""
    from .distribution import is_onefile
    if is_onefile():
        from .portable_update import create, backup_root
        return create(sys.executable, backup_root(), current_version())
    install_dir = Path(install_dir or Path(sys.executable).parent).resolve()
    executable = install_dir / 'EoingPDF.exe'
    if not executable.is_file() or not getattr(sys, 'frozen', False):
        raise ValueError(tr('실행 중인 설치 파일을 찾을 수 없어 업데이트 백업을 만들 수 없습니다.'))
    folder = Path(os.environ['LOCALAPPDATA']) / 'EoingPDF' / 'updates' / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    from .update_snapshot import create, validate
    backup = create(install_dir, folder, current_version())
    backups = []
    for item in folder.glob('snapshot-*'):
        if item.is_symlink() or item.is_junction() or not item.resolve().is_relative_to(folder.resolve()):
            continue
        try:
            validate(item, install_dir)
            backups.append(item)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for old in sorted(backups, key=lambda item: item.stat().st_mtime, reverse=True)[3:]:
        if old != backup:
            shutil.rmtree(old)
    return backup


def rollback_latest(install_dir=None):
    from .distribution import is_onefile
    if is_onefile():
        raise ValueError(tr('실행 중인 포터블은 종료 후 복구 도우미로 복원해야 합니다.'))
    install_dir = Path(install_dir or Path(sys.executable).parent).resolve()
    choice = latest_backup(install_dir)
    if choice is None:
        raise ValueError(tr('복원할 전체 업데이트 백업이 없습니다.'))
    from .update_snapshot import restore
    return restore(choice[0], install_dir)


def latest_backup(install_dir=None):
    """Return only a verified full snapshot for this installation."""
    from .distribution import is_onefile
    if is_onefile():
        from .portable_update import latest
        return latest()
    from .update_snapshot import validate
    install_dir = Path(install_dir or Path(sys.executable).parent).resolve()
    folder = Path(os.environ['LOCALAPPDATA']) / 'EoingPDF' / 'updates' / 'backups'
    choices = []
    for item in folder.glob('snapshot-*') if folder.is_dir() else ():
        if item.is_symlink() or item.is_junction():
            continue
        try:
            choices.append((item.stat().st_mtime, item))
        except OSError:
            continue
    # Validate newest first; an older snapshot cannot improve a valid result.
    for _, item in sorted(choices, reverse=True):
        try:
            manifest = validate(item, install_dir)
            verify_installer(item / 'EoingPDF.exe', manifest['files']['EoingPDF.exe'])
            return item, manifest.get('version', '')
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+){0,2}', value):
        raise ValueError(tr('올바른 버전 번호가 없습니다.'))
    parts = tuple(int(p) for p in value.split('.'))
    return parts + (0,) * (4 - len(parts))


def current_version():
    from .distribution import is_onefile, resource_root
    if is_onefile():
        return (resource_root() / 'VERSION').read_text(encoding='utf-8-sig').strip()
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    return (root / 'VERSION').read_text(encoding='utf-8-sig').strip()


def _validate_manifest_origin(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'raw.githubusercontent.com'
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.fragment
                or parsed.path != '/Eoingtilab/nalapps-releases/main/products/eoingpdf/latest.json'):
            raise ValueError()
    except (TypeError, ValueError):
        raise LicenseError(tr('업데이트 배포 정보 주소가 올바르지 않습니다.')) from None


def _release_asset_url(url, version, portable=False):
    try:
        parsed = urlsplit(url)
        expected_tag = UPDATE_RELEASE_TAG_PREFIX + version
        expected_name = (
            f'EoingPDF-{version}-portable.exe' if portable
            else f'EoingPDF-{version}-Setup-x64.exe'
        )
        expected_path = f'/Eoingtilab/nalapps-releases/releases/download/{expected_tag}/{expected_name}'
        if (parsed.scheme != 'https' or parsed.hostname != 'github.com'
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.fragment or parsed.query or parsed.path != expected_path):
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError(tr('업데이트 설치 파일의 GitHub 릴리스 주소를 확인해 주세요.')) from None
    return url


def fetch_release_manifest(opener=None):
    _validate_manifest_origin(UPDATE_MANIFEST_URL)
    opener = opener or build_opener()
    request = Request(
        UPDATE_MANIFEST_URL,
        headers={'User-Agent': f'EoingPDF/{current_version()}', 'Cache-Control': 'no-cache'},
    )
    try:
        with opener.open(request, timeout=12) as response:
            final_url = response.geturl() if hasattr(response, 'geturl') else UPDATE_MANIFEST_URL
            _validate_manifest_origin(final_url)
            payload = response.read(UPDATE_MANIFEST_MAX_BYTES + 1)
    except LicenseError:
        raise
    except (URLError, OSError, ValueError):
        raise LicenseError(tr('업데이트 배포 정보를 확인할 수 없습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.')) from None
    if len(payload) > UPDATE_MANIFEST_MAX_BYTES:
        raise LicenseError(tr('업데이트 배포 정보가 너무 큽니다.'))
    try:
        data = json.loads(payload.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise LicenseError(tr('업데이트 배포 정보 형식이 올바르지 않습니다.')) from None
    if not isinstance(data, dict) or data.get('productId') != UPDATE_PRODUCT_ID:
        raise LicenseError(tr('다른 제품의 업데이트 배포 정보입니다.'))
    return data


def validated_download(info):
    version = info.get('version')
    portable = info.get('kind') == 'portable'
    version_tuple(version)
    link = _release_asset_url(info.get('url'), version, portable=portable)
    digest = info.get('sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
        raise ValueError(tr('릴리스에 올바른 SHA-256 검증 정보가 없습니다. 업데이트를 설치하지 않았습니다.'))
    return link, digest.lower()


def update_info(current):
    state = store()
    if not state.valid_session():
        raise LicenseError(tr('활성화된 라이선스가 있어야 업데이트를 확인할 수 있습니다.'))
    data = fetch_release_manifest()
    newest = data.get('version')
    try:
        newest_tuple = version_tuple(newest)
    except ValueError:
        raise LicenseError(tr('릴리스 저장소의 버전 정보가 올바르지 않습니다.')) from None
    if newest_tuple <= version_tuple(current):
        return None
    from .distribution import is_onefile
    portable = is_onefile()
    link_key = 'portableDownloadUrl' if portable else 'downloadUrl'
    hash_key = 'portableSha256' if portable else 'sha256'
    info = {
        'version': newest,
        'url': data.get(link_key),
        'sha256': data.get(hash_key),
        'kind': 'portable' if portable else 'installer',
    }
    try:
        validated_download(info)
    except ValueError as error:
        raise LicenseError(str(error)) from None
    return info


def download(info):
    link, expected_digest = validated_download(info)
    folder = Path(os.environ['LOCALAPPDATA']) / 'EoingPDF/updates'
    folder.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='download-', suffix='.tmp', dir=folder)
    target = Path(temporary).with_suffix('.exe')
    digest = hashlib.sha256()
    size = 0
    deadline = time.monotonic() + 300
    try:
        with os.fdopen(fd, 'wb') as output:
            with build_opener().open(Request(link, headers={'User-Agent': f'EoingPDF/{current_version()}'}), timeout=20) as response:
                final_url = response.geturl() if hasattr(response, 'geturl') else link
                final = urlsplit(final_url)
                if (final.scheme != 'https'
                        or final.hostname not in {'release-assets.githubusercontent.com', 'github.com'}
                        or final.username or final.password or final.port not in (None, 443)
                        or final.fragment):
                    raise ValueError(tr('GitHub 릴리스가 아닌 주소로 이동되어 업데이트를 중단했습니다.'))
                while chunk := response.read(65536):
                    size += len(chunk)
                    if size > UPDATE_ASSET_MAX_BYTES or time.monotonic() > deadline:
                        raise ValueError(tr('업데이트 다운로드 제한을 초과했습니다.'))
                    output.write(chunk)
                    digest.update(chunk)
        with open(temporary, 'rb') as downloaded:
            if downloaded.read(2) != b'MZ' or size < 1024:
                raise ValueError(tr('Windows 설치 파일이 아닙니다.'))
        actual_digest = digest.hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(tr('업데이트 파일 검증에 실패했습니다.'))
        os.replace(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify_installer(path, expected_digest):
    if not isinstance(expected_digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_digest):
        raise ValueError(tr('업데이트 파일 검증 정보가 없습니다.'))
    digest = hashlib.sha256()
    size = 0
    with open(path, 'rb') as source:
        if source.read(2) != b'MZ':
            raise ValueError(tr('Windows 설치 파일이 아닙니다.'))
        source.seek(0)
        for chunk in iter(lambda: source.read(65536), b''):
            size += len(chunk)
            if size > UPDATE_ASSET_MAX_BYTES:
                raise ValueError(tr('업데이트 파일 크기 제한을 초과했습니다.'))
            digest.update(chunk)
    if size < 1024 or digest.hexdigest() != expected_digest.lower():
        raise ValueError(tr('업데이트 파일이 변경되었거나 검증에 실패했습니다.'))

def busy_window(window):
    from PySide6.QtWidgets import QApplication
    if QApplication.activeModalWidget() is not None:
        return True
    for widget in QApplication.topLevelWidgets():
        if getattr(widget, 'dirty', False):
            return True
        worker = getattr(widget, 'worker', None)
        if worker is not None and worker.isRunning():
            return True
        if widget.isVisible() and widget.isFullScreen():
            return True
    return False


class AutoUpdater:
    def __init__(self, app, window, auto_check=True):
        from PySide6.QtCore import QTimer
        self.app, self.window = app, window
        self.results = queue.Queue()
        self.pending = None
        self.pending_digest = None
        self.pending_backup = None
        self.latest_version = None
        self.message = tr('자동 업데이트를 확인하고 있습니다.')
        self.running = False
        self.timer = QTimer(app)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1000)
        if auto_check:
            QTimer.singleShot(1500, self.check)
        else:
            self.message = tr('복원 후 이번 실행에서는 자동 업데이트를 건너뛰었습니다.')

    def check(self):
        if self.running or self.pending:
            return
        self.running = True
        self.message = tr('자동 업데이트를 확인하고 있습니다.')
        def work():
            try:
                info = update_info(current_version())
                path = download(info) if info else None
                backup = backup_current_install() if path and getattr(sys, 'frozen', False) else None
                message = (tr('업데이트 파일과 복구 백업이 준비되었습니다.') if path else
                           tr('현재 버전보다 새로운 업데이트가 없습니다.'))
                self.results.put((path, message, info['sha256'] if info else None,
                                  info['version'] if info else None, backup,
                                  info['version'] if info else current_version()))
            except LicenseError as error:
                self.results.put((None, str(error), None))
            except Exception:
                self.results.put((None, tr('업데이트 정보를 확인하거나 설치 파일을 검증하지 못했습니다. 다음 실행 때 다시 확인합니다.'), None))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            result = self.results.get_nowait()
            self.pending, self.message, self.pending_digest = result[:3]
            self.pending_version = result[3] if len(result) > 3 else None
            self.pending_backup = result[4] if len(result) > 4 else None
            self.latest_version = result[5] if len(result) > 5 else self.latest_version
            self.running = False
        except queue.Empty:
            pass
        if self.pending and not busy_window(self.window):
            if not getattr(sys, 'frozen', False):
                self.message = tr('개발 실행에서는 자동 설치를 하지 않습니다.')
                self.pending = None
                return
            try:
                verify_installer(self.pending, self.pending_digest)
                backup = getattr(self, 'pending_backup', None)
                if backup is None:
                    raise ValueError(tr('검증된 복구 백업이 준비되지 않았습니다.'))
                from .update_helper import launch
                launch(backup, installer=self.pending, digest=self.pending_digest, version=getattr(self, 'pending_version', None))
            except ValueError:
                self.message = tr('업데이트 설치 직전 파일 검증에 실패했습니다. 다시 확인해 주세요.')
                self.pending = None
                self.pending_digest = None
                return
            except OSError:
                self.message = tr('업데이트 설치 파일을 실행하지 못했습니다.')
                self.pending = None
                return
            self.timer.stop()
            self.app.quit()


def start_updates(app, window):
    from .package_context import store_managed_updates
    if store_managed_updates():
        app.updater = None
        app.store_managed_updates = True
        return
    app.updater = AutoUpdater(app, window, auto_check='--skip-update-once' not in sys.argv)


def show_update_status(parent):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .package_context import store_managed_updates
    if store_managed_updates():
        QMessageBox.information(parent, tr('자동 업데이트'), tr('Microsoft Store 설치판은 Microsoft Store가 업데이트를 관리합니다.'))
        return
    updater = getattr(QApplication.instance(), 'updater', None)
    if updater:
        updater.check()
        explanation = tr('프로그램 실행 시 새 버전을 자동으로 내려받아 설치합니다.\n저장하지 않은 편집이나 진행 중인 작업이 있으면 적용을 기다립니다.')
        QMessageBox.information(parent, tr('자동 업데이트'), explanation + '\n\n' + updater.message)
