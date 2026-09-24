"""Verify the explicit source archive contains newly added product modules only."""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = (ROOT / 'VERSION').read_text(encoding='utf-8-sig').strip()
archive_path = ROOT / f'release/EoingPDF-{version}-source.zip'
if not archive_path.is_file():
    raise SystemExit('source archive is missing; run scripts/package_source.py first')
with zipfile.ZipFile(archive_path) as archive:
    names = set(archive.namelist())
    required = {
        'EoingPDF-source/src/eoingpdf/distribution.py',
        'EoingPDF-source/src/eoingpdf/staging_dock.py',
        'EoingPDF-source/packaging/onefile.marker',
        'EoingPDF-source/build_portable.ps1',
        'EoingPDF-source/src/eoingpdf/scan_pdf.py',
        'EoingPDF-source/src/eoingpdf/seal_vault.py',
        'EoingPDF-source/src/eoingpdf/image_replace.py',
        'EoingPDF-source/src/eoingpdf/sanitize.py',
        'EoingPDF-source/docs/QUALITY_REPORT_2.2.0.md',
        'EoingPDF-source/src/eoingpdf/search_worker.py',
        'EoingPDF-source/assets/search/model.onnx',
        'EoingPDF-source/assets/search/weights.bin',
        'EoingPDF-source/assets/search/tokenizer.json',
        'EoingPDF-source/assets/search/LICENSE-Apache-2.0.txt',
    }
    forbidden_suffixes = ('.pyc', '.exe', '.dll', '.docx', '.pdf')
    missing = sorted(required - names)
    forbidden = sorted(name for name in names if name.lower().endswith(forbidden_suffixes))
    if missing or forbidden:
        raise SystemExit(f'missing={missing} forbidden={forbidden[:5]}')
    if archive.testzip() is not None:
        raise SystemExit('source archive CRC check failed')
print(f'PASS: source archive {len(names)} entries, required modules and no private binaries')
