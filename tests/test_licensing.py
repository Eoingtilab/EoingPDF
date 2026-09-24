import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.licensing import LicenseStore, LicenseError, ITEM_ID


class LicenseTests(unittest.TestCase):
    def test_lifecycle_encryption_and_device(self):
        calls = []
        def transport(action, key, device):
            calls.append((action, key, device))
            return {'success': True, 'license': 'deactivated' if action == 'deactivate_license' else 'valid', 'item_id': ITEM_ID}
        with tempfile.TemporaryDirectory() as folder:
            store = LicenseStore(folder, transport)
            self.assertFalse(store.valid_session())
            store.perform('activate_license', 'test-license-key')
            self.assertTrue(store.valid_session())
            self.assertNotIn(b'test-license-key', (Path(folder) / 'license.dat').read_bytes())
            reopened = LicenseStore(folder, transport)
            self.assertTrue(reopened.valid_session())
            reopened.perform('check_license')
            self.assertTrue(reopened.valid_session())
            reopened.perform('deactivate_license')
            self.assertFalse(reopened.valid_session())
            reopened.perform('activate_license')
            self.assertTrue(reopened.valid_session())
            self.assertEqual(len({call[2] for call in calls}), 1)

    def test_revocation_and_failed_deactivation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LicenseStore(folder, lambda *args: {'success': True, 'license': 'valid'})
            store.perform('activate_license', 'test-key')
            store.transport = lambda *args: {'success': False, 'license': 'invalid'}
            with self.assertRaises(LicenseError):
                store.perform('deactivate_license')
            self.assertTrue(store.valid_session())
            with self.assertRaises(LicenseError):
                store.perform('check_license')
            self.assertFalse(store.valid_session())

    def test_different_key_requires_deactivation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LicenseStore(folder, lambda *args: {'success': True, 'license': 'valid'})
            store.perform('activate_license', 'first-key')
            with self.assertRaises(LicenseError):
                store.perform('activate_license', 'second-key')
            self.assertEqual(store.data['key'], 'first-key')

    def test_no_network_grant(self):
        def offline(*args):
            raise LicenseError('연결 실패')
        with tempfile.TemporaryDirectory() as folder:
            store = LicenseStore(folder, offline)
            with self.assertRaises(LicenseError):
                store.perform('activate_license', 'test-key')
            self.assertFalse(store.valid_session())
            self.assertFalse(LicenseStore(folder).valid_session())

    def test_offline_after_activation_and_persistent_revocation(self):
        def offline(*args):
            raise LicenseError('연결 실패')
        with tempfile.TemporaryDirectory() as folder:
            active = LicenseStore(folder, lambda *args: {'success': True, 'license': 'valid'})
            active.perform('activate_license', 'test-key')
            reopened = LicenseStore(folder, offline)
            self.assertTrue(reopened.valid_session())
            for action in ('check_license', 'deactivate_license'):
                with self.assertRaises(LicenseError):
                    reopened.perform(action)
                self.assertTrue(reopened.valid_session())
            reopened.transport = lambda *args: {'success': False, 'license': 'revoked'}
            with self.assertRaises(LicenseError):
                reopened.perform('check_license')
            self.assertFalse(LicenseStore(folder, offline).valid_session())

    def test_invalid_key_does_not_destroy_existing_activation(self):
        with tempfile.TemporaryDirectory() as folder:
            active = LicenseStore(folder, lambda *args: {'success': True, 'license': 'valid'})
            active.perform('activate_license', 'test-key')
            with self.assertRaises(LicenseError):
                active.perform('check_license', 'another-key')
            self.assertTrue(active.valid_session())
