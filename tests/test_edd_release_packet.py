import importlib.util
from pathlib import Path
import json
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('prepare_edd_release', Path(__file__).resolve().parents[1] / 'scripts/prepare_edd_release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def package(root, embedded_version='2.2.0'):
    (root / 'VERSION').write_text('2.2.0', encoding='utf-8')
    folder = root / 'release'
    folder.mkdir()
    for suffix in ('Setup-x64.exe', 'portable.exe'):
        (folder / f'EoingPDF-2.2.0-{suffix}').write_bytes(b'MZ-test-' + suffix.encode())
    for suffix in ('portable.zip', 'source.zip'):
        with zipfile.ZipFile(folder / f'EoingPDF-2.2.0-{suffix}', 'w') as archive:
            archive.writestr('EoingPDF/VERSION', embedded_version)
            if suffix == 'portable.zip':
                archive.writestr('EoingPDF/_internal/VERSION', embedded_version)
    return folder


def test_registration_separates_installer_and_portable_hashes(tmp_path):
    package(tmp_path)
    packet = json.loads(module.prepare(tmp_path).read_text(encoding='utf-8'))
    fields = packet['edd_response_fields']
    assert fields['sha256'] != fields['portable_sha256']
    assert fields['download_link'] is None
    assert packet['publication_status'] == 'local_only_unverified'
    assert packet['tag'] == 'v2.2.0' and packet['item_id'] == 26818
    assert packet['default_customer_asset'] == 'EoingPDF-2.2.0-Setup-x64.exe'
    assert packet['edd_git_updater']['asset_file'] == 'EoingPDF-2.2.0-Setup-x64.exe'


def test_stale_zip_does_not_replace_existing_metadata(tmp_path):
    folder = package(tmp_path, '2.1.2')
    checksums = folder / 'SHA256SUMS.txt'
    checksums.write_text('previous', encoding='utf-8')
    with pytest.raises(ValueError, match='버전'):
        module.prepare(tmp_path)
    assert checksums.read_text(encoding='utf-8') == 'previous'


def test_mixed_embedded_versions_are_rejected(tmp_path):
    folder = package(tmp_path)
    with zipfile.ZipFile(folder / 'EoingPDF-2.2.0-portable.zip', 'w') as archive:
        archive.writestr('EoingPDF/VERSION', '2.2.0')
        archive.writestr('EoingPDF/_internal/VERSION', '2.1.2')
    with pytest.raises(ValueError, match='버전'):
        module.prepare(tmp_path)
