import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
from eoingpdf.sniffer import inspect_pdf

def test_encrypted_pdf_gets_actionable_diagnostic(tmp_path):
    path = tmp_path / 'locked.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((20, 20), 'secret')
        doc.save(path, encryption=pdf.PDF_ENCRYPT_AES_256, user_pw='pw', owner_pw='owner')
    report = inspect_pdf(path, budget_ms=100)
    assert report['page_count'] == 1 and report['pages_scanned'] == 0
    assert {'PDF-LOCKED'} == {item['code'] for item in report['diagnostics']}
    assert report['diagnostics'][0]['action'] == 'decrypt'

def test_unreadable_pdf_gets_repair_diagnostic(tmp_path):
    path = tmp_path / 'broken.pdf'
    path.write_bytes(b'%PDF-1.7\nnot a valid xref\n%%EOF')
    report = inspect_pdf(path, budget_ms=100)
    assert report.get('error') and 'PDF-DAMAGED' in {item['code'] for item in report['diagnostics']}
    assert report['diagnostics'][0]['action'] == 'repair'
