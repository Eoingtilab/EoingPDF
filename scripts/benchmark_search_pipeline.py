"""Measure each real search child separately; never combine PDF and ONNX imports."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run_stage(options):
    # Read peak working set inside the process after its last operation, avoiding
    # missed short allocation spikes in an external polling sampler.
    code = """
import sys,json
sys.path.insert(0,sys.argv[1])
from eoingpdf.search_child import child_main
status=child_main()
import psutil
memory=psutil.Process().memory_info()
print(json.dumps(dict(type='measurement', peak_rss_bytes=memory.peak_wset,
    private_bytes=memory.private, pdf_loaded='pymupdf' in sys.modules,
    onnx_loaded='onnxruntime' in sys.modules)))
sys.exit(status)
"""
    started = time.perf_counter()
    process = subprocess.run([sys.executable, '-c', code, str(ROOT / 'src')],
        input=json.dumps(options), capture_output=True, text=True, encoding='utf-8', timeout=120)
    if process.returncode:
        raise RuntimeError(process.stderr)
    messages = [json.loads(line) for line in process.stdout.splitlines()]
    result = next(row for row in messages if row['type'] == 'result')
    if not result['success']:
        raise RuntimeError(result['message'])
    measurement = next(row for row in messages if row['type'] == 'measurement')
    measurement['elapsed_ms'] = (time.perf_counter() - started) * 1000
    measurement['result'] = json.loads(result['message'])
    return measurement


def main():
    model = ROOT / 'temp/search-model/external'
    with tempfile.TemporaryDirectory(prefix='eoing-search-measure-') as directory:
        folder = Path(directory)
        documents = folder / 'documents'
        documents.mkdir()
        subprocess.run([sys.executable, str(ROOT / 'scripts/evaluate_search_model.py'),
            '--make-fixture', str(documents)], check=True, capture_output=True, timeout=30)
        options = dict(model_folder=str(model), folder=str(documents),
            database=str(folder / 'search.db'), staged=str(folder / 'pending.db'),
            cancel_path=str(folder / 'cancel'))
        results = {}
        for mode in ('prepare', 'complete', 'search'):
            results[mode] = run_stage(dict(options, mode=mode, query='계정에 들어갈 암호가 기억나지 않습니다.'))
        assert results['prepare']['pdf_loaded'] and not results['prepare']['onnx_loaded']
        assert results['complete']['onnx_loaded'] and not results['complete']['pdf_loaded']
        assert results['search']['onnx_loaded'] and not results['search']['pdf_loaded']
        assert results['search']['result'] and results['search']['result'][0]['page'] == 2
    results['scope'] = 'Child process peak RSS including psutil measurement; excludes desktop UI. 30 copies of 10 pages.'
    (model / 'evaluation-staged.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: {name: value for name, value in row.items() if name != 'result'}
        for key, row in results.items() if isinstance(row, dict)}, indent=2))


if __name__ == '__main__':
    main()
