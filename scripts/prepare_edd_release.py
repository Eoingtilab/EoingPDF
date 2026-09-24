"""Prepare local EDD registration metadata; does not publish or change the server."""
import hashlib
import json
from pathlib import Path
import re
import zipfile


def prepare(root):
    root = Path(root)
    version = (root / 'VERSION').read_text(encoding='utf-8-sig').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('VERSION 형식을 확인해 주세요.')
    folder = root / 'release'
    names = [f'EoingPDF-{version}-{suffix}' for suffix in (
        'Setup-x64.exe', 'portable.exe', 'portable.zip', 'source.zip')]
    artifacts = []
    for name in names:
        path = folder / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'배포 파일이 없거나 비어 있습니다: {name}')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        artifacts.append({'name': name, 'size': path.stat().st_size, 'sha256': digest})
    for name in names[2:]:
        with zipfile.ZipFile(folder / name) as archive:
            versions = [entry for entry in archive.namelist()
                        if entry.rsplit('/', 1)[-1] == 'VERSION']
            if not versions or any(archive.read(entry).decode('utf-8-sig').strip() != version
                                   for entry in versions):
                raise ValueError(f'ZIP 내부 버전이 일치하지 않습니다: {name}')
            if archive.testzip() is not None:
                raise ValueError(f'ZIP 무결성 검사 실패: {name}')
    packet = {
        'item_id': 26818,
        'new_version': version,
        'github_repository': 'Eoingtilab/EoingPDF',
        'tag': f'v{version}',
        'default_customer_asset': names[0],
        'edd_git_updater': {
            'asset_file': names[0],
            'file_name': names[0],
            'plugin_folder_name': 'EoingPDF',
        },
        'publication_status': 'local_only_unverified',
        'license_required': True,
        'code_signing': 'deferred',
        'artifacts': artifacts,
        'edd_response_fields': {
            'new_version': version,
            'download_link': None,
            'sha256': artifacts[0]['sha256'],
            'portable_download_link': None,
            'portable_sha256': artifacts[1]['sha256'],
        },
        'download_note': '현재 앱은 app.nal.la의 HTTPS 직접 다운로드만 허용합니다. '
                         'GitHub 파일을 서버에서 가져와 제공하거나 다운로드 정책을 별도로 수정·검증해야 합니다. '
                         'null URL은 등록 가능한 완성 응답이 아닙니다.',
    }
    # Validate all inputs before replacing generated metadata.
    (folder / 'SHA256SUMS.txt').write_text(
        ''.join(f"{a['sha256']}  {a['name']}\n" for a in artifacts), encoding='utf-8')
    destination = folder / f'EDD-REGISTRATION-{version}.json'
    destination.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return destination


if __name__ == '__main__':
    print(prepare(Path(__file__).resolve().parents[1]))
