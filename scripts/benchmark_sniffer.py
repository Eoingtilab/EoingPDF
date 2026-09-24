"""Synthetic-only timing evidence; includes cold interpreter startup separately."""
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.sniffer import inspect_pdf


def main():
    folder = ROOT / 'temp/benchmarks'
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'synthetic-slides.pdf'
    with pdf.open() as doc:
        for index in range(25):
            page = doc.new_page(width=960, height=540)
            page.insert_text((40, 60), f'Synthetic slide {index + 1}')
        doc.save(source)
    engine, total = [], []
    for _ in range(20):
        engine.append(inspect_pdf(source)['elapsed_ms'])
    for _ in range(5):
        started = time.perf_counter()
        process = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--sniff-child', str(source)],
                                 capture_output=True, timeout=5, check=True,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert json.loads(process.stdout)['pages_scanned'] == 1
        total.append((time.perf_counter() - started) * 1000)
    result = {'fixture': 'synthetic 25-page text slides', 'engine_samples': len(engine),
              'engine_median_ms': round(statistics.median(engine), 3), 'engine_max_ms': max(engine),
              'cold_process_samples': len(total), 'cold_process_median_ms': round(statistics.median(total), 3),
              'cold_process_max_ms': round(max(total), 3),
              'end_to_end_30ms_met': max(total) <= 30,
              'scope': 'Local synthetic source run only; not a production or complex-document guarantee'}
    (folder / 'sniffer.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
