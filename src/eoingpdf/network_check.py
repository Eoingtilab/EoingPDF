"""Read-only license connectivity check; never activates or loads a user's key."""
import json
from pathlib import Path
import sys
import traceback
import uuid


def main(arguments):
    if len(arguments) != 2:
        return 2
    destination, nonce = Path(arguments[0]), arguments[1]
    if not 1 <= len(nonce) <= 128 or destination.exists():
        return 2
    report = {'ok': False, 'nonce': nonce, 'frozen': bool(getattr(sys, 'frozen', False)),
              'stage': 'ssl_import'}
    try:
        import ssl
        import http.client
        from urllib.request import HTTPSHandler, build_opener
        report['stage'] = 'licensing_import'
        from .licensing import ITEM_ID, request
        report['stage'] = 'verified_context'
        context = ssl.create_default_context()
        report.update(openssl=ssl.OPENSSL_VERSION,
                      certificate_verification=context.verify_mode == ssl.CERT_REQUIRED,
                      hostname_verification=context.check_hostname,
                      https_connection=hasattr(http.client, 'HTTPSConnection'),
                      https_handler=any(isinstance(handler, HTTPSHandler)
                                        for handler in build_opener().handlers))
        if not all(report[key] for key in ('certificate_verification', 'hostname_verification',
                                          'https_connection', 'https_handler')):
            raise RuntimeError('HTTPS runtime validation failed')
        # A fresh fictitious key is used only for check_license. No LicenseStore,
        # activation/deactivation, user data, credentials or redirect is involved.
        report['stage'] = 'server_check'
        result = request('check_license', 'eoingpdf-connectivity-probe-' + uuid.uuid4().hex,
                         'eoingpdf-diagnostic-' + uuid.uuid4().hex)
        status = result.get('license')
        report['server_json'] = True
        report['server_rejected_probe'] = status in ('invalid', 'missing') and result.get('success') is not True
        report['product_matches'] = result.get('item_id') in (None, False, ITEM_ID, str(ITEM_ID))
        report['ok'] = report['server_rejected_probe'] and report['product_matches']
        report['stage'] = 'complete'
    except Exception as error:
        # Do not serialize exception text, request bodies, key values or device IDs.
        report.update(error_type=type(error).__name__,
                      error_kind=getattr(error, 'kind', 'runtime'))
        report['error_frames'] = [dict(file=Path(frame.filename).name, line=frame.lineno,
                                       function=frame.name)
                                  for frame in traceback.extract_tb(error.__traceback__)]
    try:
        with destination.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    except OSError:
        return 2
    return 0 if report['ok'] else 1
