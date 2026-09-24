"""Create the public EoingPDF update manifest for Eoingtilab/nalapps-releases."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'release'
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8-sig').strip()
PRODUCT_ID = 'eoingpdf'
TAG = f'utility-eoingpdf-v{VERSION}'
BASE = f'https://github.com/Eoingtilab/nalapps-releases/releases/download/{TAG}'

if not re.fullmatch(r'\d+\.\d+\.\d+', VERSION):
    raise ValueError('VERSION must use x.y.z format')

setup = RELEASE / f'EoingPDF-{VERSION}-Setup-x64.exe'
portable = RELEASE / f'EoingPDF-{VERSION}-portable.exe'
for path in (setup, portable):
    if not path.is_file() or path.stat().st_size < 1024:
        raise FileNotFoundError(path)

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

manifest = {
    'productId': PRODUCT_ID,
    'title': '어잉PDF',
    'version': VERSION,
    'channel': 'stable',
    'versionTag': TAG,
    'downloadUrl': f'{BASE}/{setup.name}',
    'asset': setup.name,
    'sha256': sha256(setup),
    'portableDownloadUrl': f'{BASE}/{portable.name}',
    'portableAsset': portable.name,
    'portableSha256': sha256(portable),
    'releaseNotesUrl': (
        'https://github.com/Eoingtilab/nalapps-releases/blob/main/'
        f'products/{PRODUCT_ID}/{VERSION}/release-notes.md'
    ),
    'mandatory': False,
}

target = RELEASE / 'eoingpdf-latest.json'
target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(target)
