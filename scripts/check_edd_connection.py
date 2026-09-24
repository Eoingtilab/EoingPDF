"""Read-only EDD diagnostics: never print license keys, device IDs or signed URLs."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    from eoingpdf.licensing import LicenseStore, LicenseError, request, ITEM_ID
    parser = argparse.ArgumentParser()
    parser.add_argument('--online', action='store_true')
    args = parser.parse_args()
    state = LicenseStore()
    report = dict(item_id=ITEM_ID, offline_access=state.valid_session(),
                  has_saved_key=bool(state.data.get('key')), online_checked=False)
    if args.online and report['has_saved_key']:
        try:
            checked = request('check_license', state.data['key'], state.data['device'])
            version = request('get_version', state.data['key'], state.data['device'])
            number = version.get('new_version')
            digest = version.get('sha256')
            report.update(online_checked=True,
                server_license_valid=checked.get('license') == 'valid' and checked.get('success') is True,
                server_item_matches=checked.get('item_id') in (ITEM_ID, str(ITEM_ID)),
                latest_version=number if isinstance(number, str) and re.fullmatch(r'\d+\.\d+\.\d+', number) else None,
                has_download=bool(version.get('download_link') or version.get('package')),
                valid_sha256=isinstance(digest, str) and bool(re.fullmatch(r'[0-9a-fA-F]{64}', digest)))
        except LicenseError:
            report['connection_failed'] = True
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
