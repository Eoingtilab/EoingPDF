"""Repeatable local engine benchmark; excludes fixture creation and UI startup."""
from pathlib import Path
import hashlib
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf
from eoingpdf.jobs import execute

root = Path(__file__).resolve().parents[1] / 'temp/performance'
root.mkdir(parents=True, exist_ok=True)
paths = []
for index in range(20):
    path = root / f'input-{index:02}.pdf'
    with pymupdf.open() as doc:
        for page in range(10):
            doc.new_page().insert_text((48, 48), f'Document {index}, page {page}. Fast document processing preserves originals.')
        doc.save(path)
    paths.append(str(path))
before = [hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths]
started = time.perf_counter()
result = execute('merge', paths, root / 'output')
elapsed = time.perf_counter() - started
assert not result['errors'] and not result['cancelled']
with pymupdf.open(result['outputs'][0]) as doc:
    assert doc.page_count == 200
    for index, page in enumerate(doc):
        assert f'Document {index // 10}, page {index % 10}.' in page.get_text()
assert before == [hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths]
report = {'operation':'merge', 'input_files':20, 'pages':200, 'engine_seconds':round(elapsed, 3),
          'originals_unchanged':True, 'page_order_verified':True,
          'scope':'Synthetic text PDFs; excludes application launch, scans and Office conversion.'}
(root / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
