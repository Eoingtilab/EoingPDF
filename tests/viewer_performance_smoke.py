"""Local viewer measurements on generated large PDFs; never use customer files.

Run each case in a fresh process to make Windows peak working set comparable.
Offscreen Qt includes rendering / widgets, excludes OCR, network and app launch.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import pymupdf as pdf
from PIL import Image, ImageDraw
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QAbstractItemView, QPushButton
from eoingpdf.viewer import PdfViewer


def memory_usage():
    """Windows process working set, without an additional test dependency."""
    if os.name != 'nt':
        return {'rss': None, 'peak_wset': None}
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    get_process = kernel.GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    get_memory = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    get_memory.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
    get_memory.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not get_memory(get_process(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'rss': counters.WorkingSetSize, 'peak_wset': counters.PeakWorkingSetSize}


def create_fixture(path, case):
    if path.exists():
        return
    with pdf.open() as document:
        count = 1000 if case == 'text' else 50 if case == 'daily' else 60
        for index in range(count):
            page = document.new_page()
            if case in ('text', 'daily'):
                page.insert_text((40, 60), f'GENERATED PAGE {index + 1}')
                page.insert_textbox(pdf.Rect(40, 100, 560, 780),
                                    ('Daily office document. Original remains unchanged.\n' * 35), fontsize=12)
                if index % 20 == 0:
                    page.set_rotation(90)
            else:
                image = Image.new('RGB', (2000, 2800), 'white')
                draw = ImageDraw.Draw(image)
                draw.text((130, 90), f'SYNTHETIC SCAN PAGE {index + 1}', fill='black', font_size=50)
                for y in range(200, 2640, 60):
                    draw.text((130, y), f'{index + 1}: Scanned office sample with text and ruled form rows.',
                              fill='black', font_size=32)
                    draw.line((120, y + 48, 1850, y + 48), fill='#999999', width=2)
                stream = io.BytesIO()
                image.save(stream, 'JPEG', quality=82)
                page.insert_image(page.rect, stream=stream.getvalue())
        document.save(path)


def flush(app):
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=('daily', 'text', 'scan'), required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    folder = ROOT / 'temp/reliability'
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / f'generated-{args.case}.pdf'
    create_fixture(source, args.case)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    app = QApplication([])
    started = time.perf_counter()
    with patch('eoingpdf.sniffer_ui.MicroSniffer.start'), patch('eoingpdf.license_ui.ensure_license', return_value=True):
        viewer = PdfViewer(source)
        viewer.resize(960, 820)
        viewer.show()
        flush(app)
        viewer.fit_timer.stop()
        viewer.thumbnail_timer.stop()
        opened = time.perf_counter() - started
        measurements = []
        targets = list(range(1, viewer.count + 1, max(1, viewer.count // 30))) + [viewer.count]
        for target in targets:
            started = time.perf_counter()
            viewer.page.setValue(target)
            flush(app)
            viewer.fit_timer.stop()
            viewer.thumbnail_timer.stop()
            measurements.append(time.perf_counter() - started)
            assert not viewer.canvas.pixmap().isNull()
        started = time.perf_counter()
        for row in range(0, viewer.count, 4):
            viewer.thumbnails.scrollToItem(viewer.thumbnails.item(row), QAbstractItemView.PositionAtTop)
            for _ in range(3):
                viewer.fill_thumbnails()
            flush(app)
            viewer.thumbnail_timer.stop()
        traversed = time.perf_counter() - started
        memory = memory_usage()
        cards = sum(viewer.thumbnails.itemWidget(viewer.thumbnails.item(row)) is not None
                    for row in range(viewer.count))
        report = {
            'case': args.case, 'pages': viewer.count, 'file_bytes': source.stat().st_size,
            'open_seconds': round(opened, 4), 'navigation_samples': len(measurements),
            'host': {'system': sys.platform, 'python': sys.version.split()[0],
                     'pymupdf': pdf.VersionBind, 'logical_cpus': os.cpu_count()},
            'navigation_median_seconds': round(statistics.median(measurements), 4),
            'navigation_p95_seconds': round(sorted(measurements)[int((len(measurements) - 1) * .95)], 4),
            'navigation_worst_seconds': round(max(measurements), 4),
            'thumbnail_full_traversal_seconds': round(traversed, 4),
            'retained_thumbnail_cards': cards, 'thumbnail_cache_entries': len(viewer.thumbnail_cache),
            'working_set_bytes': memory['rss'], 'peak_working_set_bytes': memory['peak_wset'],
            'original_sha256': original, 'original_unchanged': hashlib.sha256(source.read_bytes()).hexdigest() == original,
            'scope': 'Fresh-process offscreen Qt; generated text / 150+ DPI scan-like JPEG PDFs; no app launch, OCR or network.',
        }
        report['retained_thumbnail_pixmap_bytes'] = sum(
            card.findChild(QPushButton, 'thumbnailPage')
                .icon().pixmap(112, 144).toImage().sizeInBytes()
            for row in range(viewer.count)
            if (card := viewer.thumbnails.itemWidget(viewer.thumbnails.item(row))) is not None)
        viewer.close()
        flush(app)
        report['working_set_after_close_bytes'] = memory_usage()['rss']
        report['retained_thumbnail_cards_after_close'] = sum(
            viewer.thumbnails.itemWidget(viewer.thumbnails.item(row)) is not None
            for row in range(viewer.thumbnails.count()))
        closed_pixmap = viewer.canvas.pixmap()
        report['page_raster_released_after_close'] = closed_pixmap is None or closed_pixmap.isNull()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
