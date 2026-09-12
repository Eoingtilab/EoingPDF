"""Explicit source inventory: never include user documents, secrets or backups."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
target = root / 'release/EoingPDF-2.0-source.zip'
folders = ('src', 'native', 'packaging', 'scripts', 'tests', 'docs', 'assets/fonts')
files = ['main.py', 'README.md', 'ROADMAP.md', 'CHANGELOG.md', 'VERSION',
         'requirements.txt', 'build_release.ps1', 'build_installer.ps1', 'install-context-menu.cmd',
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
