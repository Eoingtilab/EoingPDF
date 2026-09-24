import hashlib
import io
import os
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from eoingpdf.licensing import LicenseError
from eoingpdf.updates import (
    AutoUpdater,
    UPDATE_MANIFEST_URL,
    backup_current_install,
    download,
    fetch_release_manifest,
    rollback_latest,
    update_info,
    validated_download,
    version_tuple,
)


class Response(io.BytesIO):
    def __init__(self, payload, url):
        super().__init__(payload)
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class UpdateTests(unittest.TestCase):
    def release(self, version='2.3.0'):
        return {
            'productId': 'eoingpdf',
            'title': '??PDF',
            'version': version,
            'channel': 'stable',
            'versionTag': f'utility-eoingpdf-v{version}',
            'downloadUrl': (
                'https://github.com/Eoingtilab/nalapps-releases/releases/download/'
                f'utility-eoingpdf-v{version}/EoingPDF-{version}-Setup-x64.exe'
            ),
            'sha256': 'a' * 64,
            'portableDownloadUrl': (
                'https://github.com/Eoingtilab/nalapps-releases/releases/download/'
                f'utility-eoingpdf-v{version}/EoingPDF-{version}-portable.exe'
            ),
            'portableSha256': 'b' * 64,
            'mandatory': False,
        }

    def info(self, manifest, portable=False):
        state = Mock()
        state.valid_session.return_value = True
        with patch('eoingpdf.updates.store', return_value=state),                 patch('eoingpdf.updates.fetch_release_manifest', return_value=manifest),                 patch('eoingpdf.distribution.is_onefile', return_value=portable):
            return update_info('2.2.0')

    def test_version_comparison(self):
        self.assertGreater(version_tuple('2.10.0'), version_tuple('2.9.9'))
        self.assertEqual(version_tuple('2.2'), version_tuple('2.2.0'))
        for bad in ('', False, 'latest', '../../file', '2.0;run'):
            with self.assertRaises(ValueError):
                version_tuple(bad)

    def test_active_license_is_required_but_version_comes_from_release_repo(self):
        state = Mock()
        state.valid_session.return_value = False
        with patch('eoingpdf.updates.store', return_value=state),                 patch('eoingpdf.updates.fetch_release_manifest') as manifest:
            with self.assertRaises(LicenseError):
                update_info('2.2.0')
            manifest.assert_not_called()

        installed = self.info(self.release())
        self.assertEqual(installed['version'], '2.3.0')
        self.assertEqual(installed['kind'], 'installer')
        self.assertTrue(installed['url'].endswith('/EoingPDF-2.3.0-Setup-x64.exe'))
        portable = self.info(self.release(), portable=True)
        self.assertEqual(portable['kind'], 'portable')
        self.assertTrue(portable['url'].endswith('/EoingPDF-2.3.0-portable.exe'))

    def test_same_and_older_versions(self):
        for version in ('2.2.0', '2.1.0'):
            self.assertIsNone(self.info(self.release(version)))

    def test_manifest_origin_and_product_are_pinned(self):
        payload = b'{"productId":"eoingpdf","version":"2.3.0"}'
        opener = Mock()
        opener.open.return_value = Response(payload, UPDATE_MANIFEST_URL)
        self.assertEqual(fetch_release_manifest(opener)['productId'], 'eoingpdf')

        opener.open.return_value = Response(payload, 'https://evil.example/latest.json')
        with self.assertRaises(LicenseError):
            fetch_release_manifest(opener)

        bad = Mock()
        bad.open.return_value = Response(b'{"productId":"other"}', UPDATE_MANIFEST_URL)
        with self.assertRaises(LicenseError):
            fetch_release_manifest(bad)

    def test_release_asset_url_and_hash_are_strict(self):
        good = self.info(self.release())
        self.assertEqual(validated_download(good)[1], 'a' * 64)
        for bad_url in (
            'http://github.com/Eoingtilab/nalapps-releases/releases/download/utility-eoingpdf-v2.3.0/EoingPDF-2.3.0-Setup-x64.exe',
            'https://github.com/Eoingtilab/EoingPDF/releases/download/v2.3.0/EoingPDF-2.3.0-Setup-x64.exe',
            'https://evil.example/EoingPDF-2.3.0-Setup-x64.exe',
        ):
            broken = dict(good, url=bad_url)
            with self.assertRaises(ValueError):
                validated_download(broken)
        with self.assertRaises(ValueError):
            validated_download(dict(good, sha256='0' * 63))

    def test_download_follows_only_github_release_redirect_and_verifies_hash(self):
        payload = b'MZ' + b'0' * 4096
        digest = hashlib.sha256(payload).hexdigest()
        info = {
            'version': '2.3.0',
            'kind': 'installer',
            'url': (
                'https://github.com/Eoingtilab/nalapps-releases/releases/download/'
                'utility-eoingpdf-v2.3.0/EoingPDF-2.3.0-Setup-x64.exe'
            ),
            'sha256': digest,
        }
        opener = Mock()
        opener.open.return_value = Response(
            payload,
            'https://release-assets.githubusercontent.com/github-production-release-asset/file',
        )
        with tempfile.TemporaryDirectory() as folder,                 patch.dict(os.environ, {'LOCALAPPDATA': folder}),                 patch('eoingpdf.updates.build_opener', return_value=opener):
            result = download(info)
            self.assertEqual(result.read_bytes(), payload)

        opener.open.return_value = Response(payload, 'https://evil.example/file.exe')
        with tempfile.TemporaryDirectory() as folder,                 patch.dict(os.environ, {'LOCALAPPDATA': folder}),                 patch('eoingpdf.updates.build_opener', return_value=opener):
            with self.assertRaises(ValueError):
                download(info)

    def test_download_rejects_tampered_payload(self):
        payload = b'MZ' + b'x' * 4096
        info = {
            'version': '2.3.0',
            'kind': 'installer',
            'url': (
                'https://github.com/Eoingtilab/nalapps-releases/releases/download/'
                'utility-eoingpdf-v2.3.0/EoingPDF-2.3.0-Setup-x64.exe'
            ),
            'sha256': '0' * 64,
        }
        opener = Mock()
        opener.open.return_value = Response(
            payload,
            'https://release-assets.githubusercontent.com/github-production-release-asset/file',
        )
        with tempfile.TemporaryDirectory() as folder,                 patch.dict(os.environ, {'LOCALAPPDATA': folder}),                 patch('eoingpdf.updates.build_opener', return_value=opener):
            with self.assertRaises(ValueError):
                download(info)
            self.assertFalse(list(Path(folder).rglob('*.tmp')))

    def test_install_waits_until_idle(self):
        updater = object.__new__(AutoUpdater)
        updater.results = queue.Queue()
        updater.pending = Path('update.exe')
        updater.pending_digest = 'a' * 64
        updater.pending_backup = Path('backup')
        updater.pending_version = '2.3.0'
        updater.app = Mock()
        updater.window = Mock()
        updater.timer = Mock()
        with patch('eoingpdf.updates.busy_window', return_value=True),                 patch('eoingpdf.update_helper.launch') as launch:
            updater.poll()
            launch.assert_not_called()
        with patch('eoingpdf.updates.busy_window', return_value=False),                 patch('eoingpdf.updates.sys.frozen', True, create=True),                 patch('eoingpdf.updates.verify_installer') as verify,                 patch('eoingpdf.update_helper.launch') as launch:
            updater.poll()
            verify.assert_called_once_with(Path('update.exe'), 'a' * 64)
            launch.assert_called_once_with(
                Path('backup'), installer=Path('update.exe'), digest='a' * 64, version='2.3.0'
            )
            updater.app.quit.assert_called_once()

    def test_pending_file_tampering_blocks_install(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'installer.exe'
            payload = b'MZ' + b'a' * 2048
            path.write_bytes(payload + b'tampered')
            updater = object.__new__(AutoUpdater)
            updater.results = queue.Queue()
            updater.pending = path
            updater.pending_digest = hashlib.sha256(payload).hexdigest()
            updater.pending_backup = Path('backup')
            updater.pending_version = '2.3.0'
            updater.app, updater.window, updater.timer = Mock(), Mock(), Mock()
            with patch('eoingpdf.updates.busy_window', return_value=False),                     patch('eoingpdf.updates.sys.frozen', True, create=True),                     patch('eoingpdf.update_helper.launch') as launch:
                updater.poll()
                launch.assert_not_called()
                updater.app.quit.assert_not_called()
                self.assertIsNone(updater.pending)

    def test_backup_and_rollback_restores_verified_previous_executable(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as local:
            install = Path(root) / 'app'
            install.mkdir()
            executable = install / 'EoingPDF.exe'
            previous = b'MZ' + b'previous-version' + b'0' * 2048
            executable.write_bytes(previous)
            with patch.dict(os.environ, {'LOCALAPPDATA': local}),                     patch('eoingpdf.updates.sys.frozen', True, create=True),                     patch('eoingpdf.updates.current_version', return_value='2.2.0'),                     patch('eoingpdf.updates.sys.executable', str(executable)):
                backup = backup_current_install(install)
                executable.write_bytes(b'MZ' + b'new-version' + b'1' * 2048)
                restored = rollback_latest(install)
            self.assertEqual(restored, executable)
            self.assertEqual(executable.read_bytes(), previous)
            self.assertTrue((backup / 'manifest.json').is_file())

    def test_rollback_rejects_tampered_backup(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as local:
            install = Path(root) / 'app'
            install.mkdir()
            executable = install / 'EoingPDF.exe'
            executable.write_bytes(b'MZ' + b'previous' + b'0' * 2048)
            with patch.dict(os.environ, {'LOCALAPPDATA': local}),                     patch('eoingpdf.updates.sys.frozen', True, create=True),                     patch('eoingpdf.updates.current_version', return_value='2.2.0'),                     patch('eoingpdf.updates.sys.executable', str(executable)):
                backup = backup_current_install(install)
                (backup / 'EoingPDF.exe').write_bytes(b'MZ' + b'tampered' + b'0' * 2048)
                with self.assertRaises(ValueError):
                    rollback_latest(install)


if __name__ == '__main__':
    unittest.main()
