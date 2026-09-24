"""Build an unsigned sparse identity package. Does not register or trust it."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NAMESPACES = {
    '': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
    'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
    'uap10': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/10',
    'rescap': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities',
    'com': 'http://schemas.microsoft.com/appx/manifest/com/windows10',
    'desktop4': 'http://schemas.microsoft.com/appx/manifest/desktop/windows10/4',
    'desktop5': 'http://schemas.microsoft.com/appx/manifest/desktop/windows10/5',
}


def makeappx():
    folder = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Windows Kits/10/bin'
    versions = sorted((p for p in folder.glob('*') if re.fullmatch(r'\d+(?:\.\d+){3}', p.name)),
                      key=lambda p: tuple(map(int, p.name.split('.'))), reverse=True)
    for version in versions:
        candidate = version / 'x64/makeappx.exe'
        if candidate.is_file():
            return candidate
    raise ValueError('Windows SDK의 x64 MakeAppx.exe가 필요합니다.')


def generate_manifest(folder, version, publisher):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or any(int(v) > 65535 for v in version.split('.')):
        raise ValueError('패키지 버전을 확인해 주세요.')
    if not publisher.startswith('CN=') or len(publisher) > 8192 or any(ord(c) < 32 for c in publisher):
        raise ValueError('서명 인증서 Subject와 같은 Publisher가 필요합니다.')
    for prefix, uri in NAMESPACES.items():
        ET.register_namespace(prefix, uri)
    tree = ET.parse(ROOT / 'packaging/modern-shell/AppxManifest.xml')
    identity = tree.getroot().find(f"{{{NAMESPACES['']}}}Identity")
    identity.set('Version', version + '.0')
    identity.set('Publisher', publisher)
    tree.write(folder / 'AppxManifest.xml', encoding='utf-8', xml_declaration=True)
    assets = folder / 'Assets'
    assets.mkdir()
    with Image.open(ROOT / 'assets/app_icon.png') as image:
        image = image.convert('RGBA')
        for name, size in [('StoreLogo', 50), ('Square150x150Logo', 150), ('Square44x44Logo', 44)]:
            image.resize((size, size), Image.Resampling.LANCZOS).save(assets / (name + '.png'))


def build(output, publisher, executable=None):
    output = Path(output).resolve()
    if output.suffix.lower() != '.msix':
        raise ValueError('결과 경로는 .msix 파일이어야 합니다.')
    output.parent.mkdir(parents=True, exist_ok=True)
    version = (ROOT / 'VERSION').read_text(encoding='utf-8-sig').strip()
    tool = Path(executable) if executable else makeappx()
    with tempfile.TemporaryDirectory(prefix='eoing-shell-package-', dir=output.parent) as temporary:
        work = Path(temporary)
        content = work / 'content'
        content.mkdir()
        generate_manifest(content, version, publisher)
        draft = work / 'identity.msix'
        # Sparse package EXE/DLL paths resolve at the external installation
        # location, so MakeAppx requires /nv for external-file validation.
        subprocess.run([str(tool), 'pack', '/o', '/d', str(content), '/nv', '/p', str(draft)],
                       check=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with zipfile.ZipFile(draft) as archive:
            if archive.testzip() or 'AppxManifest.xml' not in archive.namelist():
                raise ValueError('패키지 내용 검증 실패')
        os.replace(draft, output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/modern-shell/EoingPDF.Shell.unsigned.msix')
    parser.add_argument('--publisher', default='CN=Eoingtilab')
    parser.add_argument('--makeappx', type=Path)
    args = parser.parse_args()
    print(build(args.output, args.publisher, args.makeappx))


if __name__ == '__main__':
    main()
