"""Measure hidden-window Direct2D submission; this is not display refresh FPS."""
import json
import math
from pathlib import Path
import statistics
import sys
from time import perf_counter

from PySide6.QtCore import QPointF

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.native_ink import NativeInk


def measure(width, height, workload, backend):
    strokes = [[QPointF(i / 999, .5 + .3 * math.sin(i / 30)) for i in range(1000)]]
    timings = []
    with NativeInk(backend=backend) as overlay:
        overlay.resize(0, 0, width, height)
        for frame in range(25):
            if workload == 'append':
                strokes[0].append(QPointF(.95 + frame / 1000, .5 + .03 * math.sin(frame)))
            elif workload == 'replace':
                strokes[0][0] = QPointF(frame / 1000, .5)
            start = perf_counter()
            overlay.render(strokes, 4)
            overlay.wait()
            elapsed = (perf_counter() - start) * 1000
            if frame >= 5:
                timings.append(elapsed)
    return {'width': width, 'height': height, 'workload': workload, 'backend': backend,
            'points': len(strokes[0]), 'frames': len(timings),
            'median_ms': round(statistics.median(timings), 3),
            'max_ms': round(max(timings), 3),
            'within_120fps_submission_budget': max(timings) <= 1000 / 120}


if __name__ == '__main__':
    result = {'scope': 'hidden window submission and GPU completion, not physical refresh or input latency',
              'measurements': [measure(width, height, workload, backend)
                               for backend in ['dc', 'gpu']
                               for width, height in [(1920, 1080), (3840, 2160)]
                               for workload in ['unchanged', 'append', 'replace']]}
    target = ROOT / 'temp/benchmarks/native-ink.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
