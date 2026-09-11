"""Real Windows OCR round-trip from a raster-only Korean document."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
from eoingpdf.convert import text_pdf, to_pdf
from eoingpdf.core import Request, run
from eoingpdf.summary import summarize

root = Path(__file__).resolve().parents[1] / 'temp/ocr-fixture'
root.mkdir(parents=True, exist_ok=True)
text_pdf('문서 작업은 빠르고 간편하게 처리합니다.\n원본 파일을 보호하면서 새로운 문서를 저장합니다.\n스캔 문서의 글자를 읽고 중요한 내용을 정리합니다.', root / 'original.pdf')
with pdf.open(root / 'original.pdf') as doc:
    doc[0].get_pixmap(dpi=180).save(root / 'scan.png')
to_pdf(root / 'scan.png', root / 'scan.pdf')
with pdf.open(root / 'scan.pdf') as doc:
    assert not doc[0].get_text().strip(), 'Fixture must contain no text layer'
result = run(Request('text', (str(root / 'scan.pdf'),), str(root)))
text = result.read_text(encoding='utf-8-sig')
assert '(OCR)' in text and '문서' in text and '원본' in text, repr(text)
summary = summarize(root / 'scan.pdf')
assert 'OCR 사용 페이지: 1' in summary and '[p.1]' in summary, repr(summary)
(root / 'summary.txt').write_text(summary, encoding='utf-8')
print('PASS: raster-only Korean OCR, text extraction, summary with page provenance')
