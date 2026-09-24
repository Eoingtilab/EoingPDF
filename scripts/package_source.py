"""Explicit source inventory: never include user documents, secrets or backups."""
from pathlib import Path
import zipfile
import re

root = Path(__file__).resolve().parents[1]
version = (root / 'VERSION').read_text(encoding='utf-8-sig').strip()
if not re.fullmatch(r'\d+\.\d+\.\d+', version):
    raise ValueError('VERSION 형식을 확인해 주세요.')
target = root / f'release/EoingPDF-{version}-source.zip'
folders = ('src', 'native', 'packaging', 'scripts', 'tests', 'docs', 'assets/fonts', 'assets/nalapps-sdk', 'assets/locales', 'assets/search')
files = ['main.py', 'README.md', 'ROADMAP.md', 'CHANGELOG.md', 'VERSION', 'LICENSE', '.env.example',
         'requirements.txt', 'requirements-dev.txt', 'pytest.ini', 'build_release.ps1', 'build_portable.ps1', 'build_installer.ps1', 'install-context-menu.cmd',
         'uninstall-context-menu.cmd', '.gitignore', 'assets/app_icon.png', 'assets/app_icon.ico',
         'assets/pdf_icon.png', 'assets/pdf_icon.ico']
for folder in folders:
    files.extend(str(p.relative_to(root)) for p in (root / folder).rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.obj', '.exe', '.dll'})
target.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(files):
        archive.write(root / file, 'EoingPDF-source/' + Path(file).as_posix())
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
print(target)
