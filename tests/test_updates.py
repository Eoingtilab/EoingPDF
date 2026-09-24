import sys
import unittest
import io
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.updates import version_tuple, update_info, download, AutoUpdater, backup_current_install, rollback_latest
from eoingpdf.licensing import LicenseError


class UpdateTests(unittest.TestCase):
    def test_download_validation_and_cleanup(self):
        payload = b'MZ' + b'0' * 4096
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'LOCALAPPDATA': folder}), patch('eoingpdf.updates.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(payload)
            result = download({'url': 'https://app.nal.la/test', 'sha256': hashlib.sha256(payload).hexdigest()})
            self.assertEqual(result.read_bytes(), payload)
            opener.return_value.open.return_value = io.BytesIO(payload)
            with self.assertRaises(ValueError):
                download({'url': 'https://app.nal.la/test', 'sha256': '0' * 64})
            opener.return_value.open.return_value = io.BytesIO(b'<html>error</html>')
            with self.assertRaises(ValueError):
                download({'url': 'https://app.nal.la/test', 'sha256': hashlib.sha256(b'<html>error</html>').hexdigest()})
            self.assertFalse(list(Path(folder).rglob('*.tmp')))

    def test_install_waits_until_idle(self):
        import queue
        from unittest.mock import Mock
        updater = object.__new__(AutoUpdater)
        updater.results = queue.Queue()
        updater.pending = Path('update.exe')
        updater.pending_digest = 'a' * 64
        updater.pending_backup = Path('backup')
        updater.app = Mock()
        updater.window = Mock()
        updater.timer = Mock()
        with patch('eoingpdf.updates.busy_window', return_value=True), patch('eoingpdf.update_helper.launch') as launch:
            updater.poll()
            launch.assert_not_called()
        with patch('eoingpdf.updates.busy_window', return_value=False), patch('eoingpdf.updates.sys.frozen', True, create=True), patch('eoingpdf.updates.verify_installer') as verify, patch('eoingpdf.updates.backup_current_install', return_value=Path('backup')) as backup, patch('eoingpdf.update_helper.launch') as launch:
            updater.poll()
            verify.assert_called_once_with(Path('update.exe'), 'a' * 64)
            launch.assert_called_once_with(Path('backup'), installer=Path('update.exe'), digest='a' * 64, version=None)
            backup.assert_not_called()
            updater.app.quit.assert_called_once()

    def info(self, response):
        with patch('eoingpdf.updates.store') as state, patch('eoingpdf.updates.request', return_value=response):
            state.return_value.data = {'key': 'test-key', 'device': 'test-device'}
            return update_info('2.2.0')

    def test_version_comparison(self):
        self.assertGreater(version_tuple('2.10.0'), version_tuple('2.9.9'))
        self.assertEqual(version_tuple('2.2'), version_tuple('2.2.0'))
        for bad in ('', False, 'latest', '../../file', '2.0;run'):
            with self.assertRaises(ValueError):
                version_tuple(bad)

    def test_same_and_older_versions(self):
        for version in ('2.2.0', '2.1.0'):
            self.assertIsNone(self.info({'new_version': version}))

    def test_missing_version_is_not_reported_as_up_to_date(self):
        for response in ({}, {'new_version': ''}, {'new_version': False}, {'new_version': None}):
            with self.assertRaisesRegex(LicenseError, '버전 정보'):
                self.info(response)

    def test_trusted_update_link_only(self):
        good = self.info({'new_version': '2.3.0', 'download_link': 'https://app.nal.la/?eddfile=test', 'sha256': 'A' * 64})
        self.assertEqual(good['version'], '2.3.0')
        for url in ('http://app.nal.la/a', 'https://evil.example/a', 'file:///a.exe', 'https://app.nal.la@evil.example/a', 'https://user:pass@app.nal.la/a'):
            with self.assertRaises(LicenseError):
                self.info({'new_version': '2.3.0', 'download_link': url})

    def test_missing_or_invalid_hash_never_downloads(self):
        for digest in (None, '', False, 'a' * 63, 'g' * 64, 'a' * 64 + '\n'):
            with patch('eoingpdf.updates.build_opener') as opener:
                with self.assertRaises(ValueError):
                    download({'url': 'https://app.nal.la/test', 'sha256': digest})
                opener.assert_not_called()
            with self.assertRaises(LicenseError):
                self.info({'new_version': '2.3.0', 'download_link': 'https://app.nal.la/test', 'sha256': digest})

    def test_download_revalidates_origin(self):
        for url in ('https://evil.example/a', 'https://app.nal.la:abc/a',
                    'https://app.nal.la/a#fragment', 'https://app.nal.la/\na'):
            with patch('eoingpdf.updates.build_opener') as opener:
                with self.assertRaises(ValueError):
                    download({'url': url, 'sha256': 'a' * 64})
                opener.assert_not_called()

    def test_pending_file_tampering_blocks_install(self):
        import queue
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'installer.exe'
            payload = b'MZ' + b'a' * 2048
            path.write_bytes(payload + b'tampered')
            updater = object.__new__(AutoUpdater)
            updater.results = queue.Queue()
            updater.pending = path
            updater.pending_digest = hashlib.sha256(payload).hexdigest()
            updater.app, updater.window, updater.timer = Mock(), Mock(), Mock()
            with patch('eoingpdf.updates.busy_window', return_value=False), patch('eoingpdf.updates.sys.frozen', True, create=True), patch('eoingpdf.update_helper.launch') as launch:
                updater.poll()
                launch.assert_not_called()
                updater.app.quit.assert_not_called()
                self.assertIsNone(updater.pending)

    def test_backup_and_rollback_restores_verified_previous_executable(self):
        import os
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as local:
            install = Path(root) / 'app'
            install.mkdir()
            executable = install / 'EoingPDF.exe'
            previous = b'MZ' + b'previous-version' + b'0' * 2048
            executable.write_bytes(previous)
            environment = {'LOCALAPPDATA': local}
            with patch.dict(os.environ, environment), patch('eoingpdf.updates.sys.frozen', True, create=True), patch('eoingpdf.updates.current_version', return_value='2.2.0'), patch('eoingpdf.updates.sys.executable', str(executable)):
                backup = backup_current_install(install)
                executable.write_bytes(b'MZ' + b'new-version' + b'1' * 2048)
                restored = rollback_latest(install)
            self.assertEqual(restored, executable)
            self.assertEqual(executable.read_bytes(), previous)
            self.assertTrue((backup / 'manifest.json').is_file())

    def test_rollback_rejects_tampered_backup(self):
        import os
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as local:
            install = Path(root) / 'app'
            install.mkdir()
            executable = install / 'EoingPDF.exe'
            executable.write_bytes(b'MZ' + b'previous' + b'0' * 2048)
            with patch.dict(os.environ, {'LOCALAPPDATA': local}), patch('eoingpdf.updates.sys.frozen', True, create=True), patch('eoingpdf.updates.current_version', return_value='2.2.0'), patch('eoingpdf.updates.sys.executable', str(executable)):
                backup = backup_current_install(install)
                (backup / 'EoingPDF.exe').write_bytes(b'MZ' + b'tampered' + b'0' * 2048)
                with self.assertRaises(ValueError):
                    rollback_latest(install)
