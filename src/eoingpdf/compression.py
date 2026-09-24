"""Measured target-size compression preserving PDF text and vector content."""
from .localization import tr
import math
import io
import shutil
import tempfile
from pathlib import Path
import pymupdf as pdf
from PIL import Image
from .core import Cancelled


def resize_opaque_images(document, dpi, quality, cancelled):
    placements = {}
    for page in document:
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        for item in page.get_image_info(xrefs=True):
            xref = item['xref']
            if not xref:
                continue
            matrix = pdf.Matrix(item['transform'])
            width = math.hypot(matrix.a, matrix.b)
            height = math.hypot(matrix.c, matrix.d)
            scale = min(1, max(width * dpi / 72 / item['width'],
                               height * dpi / 72 / item['height']))
            previous = placements.get(xref)
            if previous is None or scale > previous[1]:
                placements[xref] = (page.number, scale)
    for xref, (page_number, scale) in placements.items():
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        if scale >= .99:
            continue
        # Preserve transparency and stencil masks; these need a separate lossless path.
        if any(document.xref_get_key(xref, key)[0] != 'null' for key in ('SMask', 'Mask')):
            continue
        if document.xref_get_key(xref, 'ImageMask') == ('bool', 'true'):
            continue
        info = document.extract_image(xref)
        if not info or info['width'] * info['height'] > 40_000_000:
            continue
        with Image.open(io.BytesIO(info['image'])) as original:
            if original.mode not in ('RGB', 'L'):
                continue
            resized = original.resize((max(1, round(original.width * scale)),
                                       max(1, round(original.height * scale))), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            resized.save(stream, format='JPEG', quality=quality, optimize=True)
            document[page_number].replace_image(xref, stream=stream.getvalue())


def compress(document, target, target_mb, cancelled=lambda: False, progress=lambda value: None):
    if not isinstance(target_mb, (int, float)) or isinstance(target_mb, bool) or not math.isfinite(target_mb) or not .05 <= target_mb <= 2000:
        raise ValueError(tr('목표 용량은 0.05MB부터 2000MB 사이로 입력해 주세요.'))
    limit = int(target_mb * 1024 * 1024)
    target = Path(target)
    with tempfile.TemporaryDirectory(prefix='.eoing-compress-', dir=target.parent) as temporary:
        folder = Path(temporary)
        baseline = folder / 'baseline.pdf'
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        document.save(baseline, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_NONE)
        original_size = baseline.stat().st_size
        if original_size <= limit:
            shutil.copyfile(baseline, target)
            return {'bytes': original_size, 'dpi': None, 'quality': None, 'trials': 0}
        ladder = [(300, 90), (240, 85), (180, 80), (150, 70), (120, 60), (96, 50), (72, 40)]
        estimate = 300 * math.sqrt(limit / original_size)
        start = min(range(len(ladder)), key=lambda index: abs(ladder[index][0] - estimate))
        visited = set()
        best = None
        smallest = original_size
        index = start
        while 0 <= index < len(ladder) and index not in visited:
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            visited.add(index)
            dpi, quality = ladder[index]
            candidate = folder / f'candidate-{index}.pdf'
            # Every trial starts from the original optimized PDF, avoiding cumulative JPEG loss.
            with pdf.open(baseline) as trial:
                resize_opaque_images(trial, dpi, quality, cancelled)
                trial.rewrite_images(dpi_threshold=dpi + 1, dpi_target=dpi, quality=quality,
                                     lossy=True, lossless=True, bitonal=False, color=True, gray=True)
                trial.save(candidate, garbage=4, deflate=True)
            size = candidate.stat().st_size
            smallest = min(smallest, size)
            progress(int(len(visited) / len(ladder) * 90))
            if size <= limit:
                best = candidate, size, dpi, quality
                index -= 1
            elif best is not None:
                break
            else:
                index += 1
        if best is None:
            raise ValueError(tr('목표 용량에 도달하지 못했습니다. 측정한 최소 용량은 {v0:.2f}MB입니다. 목표를 늘려 주세요.', v0=smallest / 1048576))
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        candidate, size, dpi, quality = best
        with pdf.open(candidate) as verification:
            if len(verification) != len(document):
                raise ValueError(tr('압축 결과의 페이지 수 검증에 실패했습니다.'))
        shutil.copyfile(candidate, target)
        return {'bytes': size, 'dpi': dpi, 'quality': quality, 'trials': len(visited)}
