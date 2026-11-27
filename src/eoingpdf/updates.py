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
    from .product_policy import LICENSE_REQUIRED
    if LICENSE_REQUIRED and not store().valid_session():
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
        self.pending_version = None
        self.pending_backup = None
        self.latest_version = None
        self.confirm_restart = True
        self.apply_on_close = False
        self.notice_dismissed = False
        self._banner = None
        self.message = tr('자동 업데이트를 확인하고 있습니다.')
        self.running = False
        self.timer = QTimer(app)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1000)
        if auto_check:
            QTimer.singleShot(1500, self.check)
        else:
            self.message = tr('복원 후 이번 실행에서는 자동 업데이트를 건너뛰었습니다.')

    def attach_banner(self, banner):
        self._banner = banner
        self._sync_banner()

    def _sync_banner(self):
        banner = getattr(self, '_banner', None)
        if banner is not None:
            banner.sync_from_updater(self)

    def check(self):
        if self.running or self.pending:
            return
        self.running = True
        self.notice_dismissed = False
        self.message = tr('자동 업데이트를 확인하고 있습니다.')
        self._sync_banner()

        def work():
            try:
                info = update_info(current_version())
                if info:
                    self.latest_version = info['version']
                    self.message = tr('새 버전 {version}을 다운로드하고 있습니다…', version=info['version'])
                path = download(info) if info else None
                backup = backup_current_install() if path and getattr(sys, 'frozen', False) else None
                message = (tr('새 버전 {version} 다운로드 완료 · 업데이트가 준비되었습니다.', version=info['version']) if path else
                           tr('현재 버전보다 새로운 업데이트가 없습니다.'))
                self.results.put((path, message, info['sha256'] if info else None,
                                  info['version'] if info else None, backup,
                                  info['version'] if info else current_version()))
            except LicenseError as error:
                self.results.put((None, str(error), None))
            except Exception:
                self.results.put((None, tr('업데이트 정보를 확인하거나 설치 파일을 검증하지 못했습니다. 다음 실행 때 다시 확인합니다.'), None))

        threading.Thread(target=work, daemon=True).start()

    def _install_pending(self, restart=True):
        if not self.pending:
            return False
        if not getattr(sys, 'frozen', False):
            self.message = tr('개발 실행에서는 자동 설치를 하지 않습니다.')
            self.pending = None
            self._sync_banner()
            return False
        try:
            verify_installer(self.pending, self.pending_digest)
            backup = getattr(self, 'pending_backup', None)
            if backup is None:
                raise ValueError(tr('검증된 복구 백업이 준비되지 않았습니다.'))
            from .update_helper import launch
            kwargs = dict(installer=self.pending, digest=self.pending_digest,
                          version=getattr(self, 'pending_version', None))
            if not restart:
                kwargs['restart'] = False
            launch(backup, **kwargs)
        except ValueError:
            self.message = tr('업데이트 설치 직전 파일 검증에 실패했습니다. 다시 확인해 주세요.')
            self.pending = None
            self.pending_digest = None
            self._sync_banner()
            return False
        except OSError:
            self.message = tr('업데이트 설치 파일을 실행하지 못했습니다.')
            self.pending = None
            self._sync_banner()
            return False
        if hasattr(self, 'timer') and self.timer is not None:
            self.timer.stop()
        if restart and getattr(self, 'app', None) is not None:
            self.app.quit()
        return True

    def apply_pending_now(self):
        if not getattr(self, 'pending', None):
            return False
        if busy_window(self.window):
            from PySide6.QtWidgets import QMessageBox
            self.message = tr('저장하지 않은 변경이나 진행 중인 작업을 마친 뒤 업데이트할 수 있습니다.')
            self._sync_banner()
            QMessageBox.information(self.window, tr('자동 업데이트'), self.message)
            return False
        return self._install_pending(restart=True)

    def defer_until_close(self):
        if not getattr(self, 'pending', None):
            return
        self.apply_on_close = True
        self.notice_dismissed = False
        ver = getattr(self, 'pending_version', None) or getattr(self, 'latest_version', '') or ''
        self.message = tr('창을 닫으면 새 버전 {version}으로 자동 업데이트합니다.', version=ver)
        self._sync_banner()

    def dismiss_notice(self):
        self.notice_dismissed = True
        self.apply_on_close = False
        self._sync_banner()

    def flush_on_close(self):
        if getattr(self, 'pending', None) and getattr(self, 'apply_on_close', False) and getattr(sys, 'frozen', False):
            return self._install_pending(restart=False)
        return False

    def poll(self):
        try:
            result = self.results.get_nowait()
            self.pending, self.message, self.pending_digest = result[:3]
            self.pending_version = result[3] if len(result) > 3 else None
            self.pending_backup = result[4] if len(result) > 4 else None
            self.latest_version = result[5] if len(result) > 5 else self.latest_version
            self.running = False
            self.notice_dismissed = False
            self._sync_banner()
        except queue.Empty:
            if getattr(self, 'running', False):
                self._sync_banner()
        if self.pending and not busy_window(self.window):
            if getattr(self, 'confirm_restart', False):
                self._sync_banner()
                return
            self._install_pending(restart=True)


def attach_update_banner(window, updated_to=''):
    """Create and attach a non-intrusive top update notification strip to any main window."""
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy
    from .action_icons import set_action_icon
    from .sdk_theme import apply_style

    class _Banner(QFrame):
        def __init__(self, host_window):
            super().__init__(host_window)
            self.host_window = host_window
            self._updated_version = ''
            self.setObjectName('updateBanner')
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(14, 7, 14, 7)
            layout.setSpacing(8)
            self.text = QLabel()
            self.text.setWordWrap(True)
            layout.addWidget(self.text, 1)

            self.install_btn = QPushButton(tr('지금 업데이트'))
            set_action_icon(self.install_btn, 'update')
            self.install_btn.setAutoDefault(False)
            self.install_btn.clicked.connect(self._apply_now)
            layout.addWidget(self.install_btn)

            self.defer_btn = QPushButton(tr('닫을 때 적용'))
            set_action_icon(self.defer_btn, 'history')
            self.defer_btn.setAutoDefault(False)
            self.defer_btn.clicked.connect(self._defer_close)
            layout.addWidget(self.defer_btn)

            self.whats_new_btn = QPushButton(tr('단축키 안내'))
            set_action_icon(self.whats_new_btn, 'list')
            self.whats_new_btn.setAutoDefault(False)
            self.whats_new_btn.clicked.connect(self._show_shortcuts)
            layout.addWidget(self.whats_new_btn)

            self.dismiss_btn = QPushButton()
            set_action_icon(self.dismiss_btn, 'close')
            self.dismiss_btn.setFixedSize(28, 28)
            self.dismiss_btn.setToolTip(tr('알림 닫기'))
            apply_style(self.dismiss_btn, 'QPushButton {padding:0;border:0;background:#edf2ff;}')
            self.dismiss_btn.clicked.connect(self._dismiss)
            layout.addWidget(self.dismiss_btn)
            self.hide()

        def _updater(self):
            from PySide6.QtWidgets import QApplication
            return getattr(QApplication.instance(), 'updater', None)

        def _apply_now(self):
            updater = self._updater()
            if updater is not None:
                updater.apply_pending_now()

        def _defer_close(self):
            updater = self._updater()
            if updater is not None:
                updater.defer_until_close()

        def _show_shortcuts(self):
            if hasattr(self.host_window, 'open_shortcuts_dialog'):
                self.host_window.open_shortcuts_dialog()

        def _dismiss(self):
            self._updated_version = ''
            updater = self._updater()
            if updater is not None:
                updater.dismiss_notice()
            self.hide()

        def show_updated(self, version: str):
            self._updated_version = str(version or current_version())
            self.text.setText(tr('어잉PDF {version} 버전으로 업데이트가 완료되었습니다!', version=self._updated_version))
            apply_style(
                self,
                'QFrame#updateBanner {background:#ecf6f2;border-bottom:1px solid #c6d3e6;}'
                'QLabel {color:#458475;font-weight:600;font-size:12px;}',
            )
            self.install_btn.hide()
            self.defer_btn.hide()
            self.whats_new_btn.setVisible(hasattr(self.host_window, 'open_shortcuts_dialog'))
            self.dismiss_btn.show()
            self.show()

        def sync_from_updater(self, updater):
            if getattr(updater, 'notice_dismissed', False) and not self._updated_version:
                self.hide()
                return
            if updater.pending:
                self._updated_version = ''
                ver = getattr(updater, 'pending_version', None) or getattr(updater, 'latest_version', '') or ''
                apply_style(
                    self,
                    'QFrame#updateBanner {background:#edf2ff;border-bottom:1px solid #c6d3e6;}'
                    'QLabel {color:#183b8f;font-weight:600;font-size:12px;}',
                )
                if getattr(updater, 'apply_on_close', False):
                    self.text.setText(tr('창을 닫으면 새 버전 {version}으로 자동 업데이트합니다.', version=ver))
                    self.defer_btn.hide()
                    self.install_btn.setText(tr('지금 업데이트'))
                    self.install_btn.setVisible(getattr(sys, 'frozen', False))
                else:
                    self.text.setText(tr('새 버전 {version} 다운로드 완료 — 지금 업데이트할까요?', version=ver))
                    self.install_btn.setText(tr('지금 업데이트'))
                    self.install_btn.setVisible(getattr(sys, 'frozen', False))
                    self.defer_btn.setVisible(getattr(sys, 'frozen', False))
                self.whats_new_btn.hide()
                self.dismiss_btn.show()
                self.show()
            elif updater.running and getattr(updater, 'latest_version', None) and getattr(updater, 'latest_version', current_version()) != current_version():
                self._updated_version = ''
                apply_style(
                    self,
                    'QFrame#updateBanner {background:#f7f9fc;border-bottom:1px solid #c6d3e6;}'
                    'QLabel {color:#416ae6;font-weight:600;font-size:12px;}',
                )
                self.text.setText(updater.message)
                self.install_btn.hide()
                self.defer_btn.hide()
                self.whats_new_btn.hide()
                self.dismiss_btn.show()
                self.show()
            elif not self._updated_version:
                self.hide()

    banner = getattr(window, '_update_banner', None)
    if banner is None:
        banner = _Banner(window)
        window._update_banner = banner
        host_layout = getattr(window, 'update_banner_host', None)
        if host_layout is not None:
            host_layout.addWidget(banner)
        elif hasattr(window, 'layout') and window.layout() is not None:
            window.layout().insertWidget(0, banner)
    if updated_to:
        banner.show_updated(updated_to)
    return banner


def start_updates(app, window, updated_to=''):
    banner = attach_update_banner(window, updated_to=updated_to)
    from .package_context import store_managed_updates
    if store_managed_updates():
        app.updater = None
        app.store_managed_updates = True
        return
    app.updater = AutoUpdater(app, window, auto_check='--skip-update-once' not in sys.argv)
    app.updater.attach_banner(banner)


def show_update_status(parent):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox,
        QProgressBar, QPushButton, QVBoxLayout,
    )
    from .package_context import store_managed_updates
    if store_managed_updates():
        QMessageBox.information(parent, tr('자동 업데이트'), tr('Microsoft Store 설치판은 Microsoft Store가 업데이트를 관리합니다.'))
        return

    updater = getattr(QApplication.instance(), 'updater', None)
    dialog = QDialog(parent)
    dialog.setWindowTitle(tr('자동 업데이트'))
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)

    current = current_version()
    intro = QLabel(tr('프로그램 실행 시 새 버전을 자동으로 내려받아 설치합니다.\n저장하지 않은 편집이나 진행 중인 작업이 있으면 적용을 기다립니다.'))
    intro.setWordWrap(True)
    layout.addWidget(intro)

    version_label = QLabel(tr('현재 설치 버전: {version}', version=current))
    layout.addWidget(version_label)

    status_label = QLabel(tr('자동 업데이트를 확인하고 있습니다.'))
    status_label.setWordWrap(True)
    layout.addWidget(status_label)

    progress = QProgressBar()
    progress.setRange(0, 0)
    progress.setMaximumHeight(6)
    layout.addWidget(progress)

    buttons = QHBoxLayout()
    recheck_btn = QPushButton(tr('다시 확인'))
    install_btn = QPushButton(tr('지금 설치 후 재시작'))
    install_btn.setObjectName('primary')
    install_btn.hide()
    close_btn = QPushButton(tr('닫기'))
    buttons.addWidget(recheck_btn)
    buttons.addStretch(1)
    buttons.addWidget(install_btn)
    buttons.addWidget(close_btn)
    layout.addLayout(buttons)

    standalone_state = {'running': False, 'message': '', 'latest': current}

    def run_standalone_check():
        if standalone_state['running']:
            return
        standalone_state['running'] = True
        standalone_state['message'] = tr('자동 업데이트를 확인하고 있습니다.')
        def worker():
            try:
                info = update_info(current)
                if info:
                    standalone_state['latest'] = info['version']
                    standalone_state['message'] = tr('새 버전 {version}이 출시되었습니다. 공식 설치 환경에서 자동 업데이트됩니다.', version=info['version'])
                else:
                    standalone_state['latest'] = current
                    standalone_state['message'] = tr('현재 버전보다 새로운 업데이트가 없습니다.')
            except LicenseError as error:
                standalone_state['message'] = str(error)
            except Exception:
                standalone_state['message'] = tr('업데이트 정보를 확인하거나 설치 파일을 검증하지 못했습니다. 다음 실행 때 다시 확인합니다.')
            finally:
                standalone_state['running'] = False
        threading.Thread(target=worker, daemon=True).start()

    def refresh_ui():
        if updater is not None:
            latest = getattr(updater, 'latest_version', None) or current
            version_label.setText(tr('현재 설치 버전: {current} · 서버 최신 버전: {latest}', current=current, latest=latest))
            status_label.setText(updater.message)
            running = bool(updater.running)
            progress.setRange(0, 0 if running else 100)
            if not running:
                progress.setValue(100)
            recheck_btn.setEnabled(not running)
            install_btn.setVisible(bool(updater.pending and getattr(sys, 'frozen', False)))
        else:
            version_label.setText(tr('현재 설치 버전: {current} · 서버 최신 버전: {latest}', current=current, latest=standalone_state['latest']))
            status_label.setText(standalone_state['message'])
            running = standalone_state['running']
            progress.setRange(0, 0 if running else 100)
            if not running:
                progress.setValue(100)
            recheck_btn.setEnabled(not running)

    def trigger_recheck():
        if updater is not None:
            if not updater.running and not updater.pending:
                updater.check()
        else:
            run_standalone_check()
        refresh_ui()

    def trigger_install_now():
        if updater is not None and updater.pending:
            dialog.accept()
            updater.apply_pending_now()

    recheck_btn.clicked.connect(trigger_recheck)
    install_btn.clicked.connect(trigger_install_now)
    close_btn.clicked.connect(dialog.accept)

    poll_timer = QTimer(dialog)
    poll_timer.timeout.connect(refresh_ui)
    poll_timer.start(200)
    trigger_recheck()
    dialog.exec()
