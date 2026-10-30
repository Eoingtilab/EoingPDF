"""License HTTPS transport, error separation and read-only frozen probe contract."""
import json
import ssl
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from urllib.request import HTTPSHandler

import pytest

from eoingpdf import licensing, network_check


def response_opener(payload):
    response = MagicMock()
    response.read.return_value = payload
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value = response
    return opener


def test_https_uses_verified_context_and_blocks_redirects(tmp_path, monkeypatch):
    monkeypatch.setenv('EOINGPDF_NETWORK_DIAG', '1')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('TEMP', str(tmp_path))
    result = {'success': False, 'license': 'invalid', 'item_id': 26818}
    opener = response_opener(json.dumps(result).encode())
    with patch.object(licensing, 'build_opener', return_value=opener) as build:
        assert licensing.request('check_license', 'fictitious-test-key', 'eoingpdf-test') == result
    handlers = build.call_args.args
    assert any(isinstance(handler, licensing.NoRedirect) for handler in handlers)
    https = next(handler for handler in handlers if isinstance(handler, HTTPSHandler))
    assert https._context.verify_mode == ssl.CERT_REQUIRED
    assert https._context.check_hostname is True
    req = opener.open.call_args.args[0]
    assert req.full_url == 'https://app.nal.la/'
    assert parse_qs(req.data.decode())['edd_action'] == ['check_license']
    assert opener.open.call_args.kwargs['timeout'] == 12
    assert list(tmp_path.iterdir()) == []  # Temporary diagnostic logging is gone.


@pytest.mark.parametrize(('error', 'kind'), [
    (HTTPError('https://app.nal.la/', 503, 'server error', {}, None), 'server'),
    (URLError('offline fictitious-test-key'), 'connection'),
    (TimeoutError('timeout'), 'connection'),
    (URLError(ssl.SSLCertVerificationError('untrusted certificate')), 'tls'),
    (ssl.SSLError('TLS handshake failed'), 'tls'),
])
def test_connection_tls_and_server_errors_are_separate_from_key_rejection(error, kind):
    with patch.object(licensing, 'build_opener') as build:
        build.return_value.open.side_effect = error
        with pytest.raises(licensing.LicenseError) as caught:
            licensing.request('check_license', 'fictitious-test-key', 'eoingpdf-test')
    assert caught.value.kind == kind
    assert 'fictitious-test-key' not in str(caught.value)


@pytest.mark.parametrize('payload', [b'<html>error</html>', b'[]', b'"invalid"', b'x' * 65537],
                         ids=['html', 'array', 'string', 'oversized'])
def test_malformed_and_oversized_json_are_response_errors(payload):
    with patch.object(licensing, 'build_opener', return_value=response_opener(payload)):
        with pytest.raises(licensing.LicenseError) as caught:
            licensing.request('check_license', 'fictitious-test-key', 'eoingpdf-test')
    assert caught.value.kind == 'response'


def test_redirect_is_rejected_without_resending_credentials():
    with pytest.raises(licensing.LicenseError) as caught:
        licensing.NoRedirect().redirect_request(None, None, 302, 'redirect', {}, 'https://example.com/')
    assert caught.value.kind == 'redirect'


def test_network_probe_only_checks_fictitious_key_without_loading_store(tmp_path):
    target = tmp_path / 'probe.json'
    with patch.object(licensing, 'request', return_value={'success': False, 'license': 'invalid'}) as request:
        with patch.object(licensing, 'LicenseStore', side_effect=AssertionError('must not load store')):
            assert network_check.main([str(target), 'probe-nonce']) == 0
    action, key, device = request.call_args.args
    assert action == 'check_license'
    assert key.startswith('eoingpdf-connectivity-probe-')
    assert device.startswith('eoingpdf-diagnostic-')
    report = json.loads(target.read_text())
    assert report['ok'] and report['certificate_verification'] and report['hostname_verification']
    assert key not in target.read_text() and device not in target.read_text()
    assert not (tmp_path / 'license.dat').exists()


def test_network_probe_records_no_grant_on_failure_and_does_not_overwrite(tmp_path):
    target = tmp_path / 'probe.json'
    with patch.object(licensing, 'request', side_effect=licensing.LicenseError('private value', kind='tls')):
        assert network_check.main([str(target), 'probe-nonce']) == 1
    report = json.loads(target.read_text())
    assert not report['ok'] and report['error_kind'] == 'tls'
    assert 'private value' not in target.read_text()
    original = target.read_bytes()
    with patch.object(licensing, 'request') as request:
        assert network_check.main([str(target), 'probe-nonce']) == 2
        request.assert_not_called()
    assert target.read_bytes() == original
