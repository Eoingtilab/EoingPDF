from unittest.mock import patch

from eoingpdf import license_ui


def test_free_access_never_loads_or_modifies_existing_license():
    with patch('eoingpdf.product_policy.LICENSE_REQUIRED', False), \
         patch('eoingpdf.license_ui.store', side_effect=AssertionError('license store accessed')), \
         patch('eoingpdf.license_ui.LicenseDialog', side_effect=AssertionError('dialog opened')):
        assert license_ui.ensure_license()
        assert license_ui.main() == 0


def test_reenabled_policy_keeps_existing_license_gate():
    with patch('eoingpdf.product_policy.LICENSE_REQUIRED', True), \
         patch('eoingpdf.license_ui.store') as store:
        store.return_value.valid_session.return_value = True
        assert license_ui.ensure_license()
        store.assert_called_once()
