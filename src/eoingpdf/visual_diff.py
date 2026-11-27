"""Page-index visual comparison at a common physical scale, bounded raster size."""
from .localization import tr
from dataclasses import dataclass
import math
import numpy as np
import pymupdf as pdf
from .core import open_pdf


@dataclass(frozen=True)
class Difference:
    before: np.ndarray
    after: np.ndarray
    highlighted: np.ndarray
    changed_pixels: int
    missing_before: bool
    missing_after: bool


def compare(before, after, page_index=0, max_side=1600, threshold=20, before_password='', after_password=''):
    if type(page_index) is not int or page_index < 0:
        raise ValueError(tr('올바른 페이지를 선택해 주세요.'))
    if not 64 <= max_side <= 2400 or not 0 <= threshold <= 255:
        raise ValueError(tr('비교 해상도 또는 차이 기준이 범위를 벗어났습니다.'))
    with open_pdf(before, before_password) as left, open_pdf(after, after_password) as right:
        if page_index >= max(len(left), len(right)):
            raise ValueError(tr('비교할 페이지가 없습니다.'))
        pages = [doc[page_index] if page_index < len(doc) else None for doc in (left, right)]
        width = max(page.rect.width for page in pages if page is not None)
        height = max(page.rect.height for page in pages if page is not None)
        scale = min(2, max_side / max(width, height))
        shape = math.ceil(height * scale), math.ceil(width * scale), 3
        rasters = []
        for page in pages:
            image = np.full(shape, 255, dtype=np.uint8)
            if page is not None:
                pixmap = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
                pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
                h, w = min(shape[0], pixmap.height), min(shape[1], pixmap.width)
                image[:h, :w] = pixels[:h, :w]
            rasters.append(image)
        old, new = rasters
        changed = np.max(np.abs(old.astype(np.int16) - new.astype(np.int16)), axis=2) > threshold
        old_ink = old.min(axis=2) < 245
        new_ink = new.min(axis=2) < 245
        highlight = ((old.astype(np.uint16) + new.astype(np.uint16)) // 2).astype(np.uint8)
        highlight[changed & old_ink & ~new_ink] = (215, 50, 65)
        highlight[changed & new_ink & ~old_ink] = (20, 150, 95)
        highlight[changed & old_ink & new_ink] = (125, 65, 195)
        return Difference(old, new, highlight, int(changed.sum()), pages[0] is None, pages[1] is None)


def compare_text(before, after, before_password='', after_password=''):
    """Return page-by-page unified text diff summary between two PDF files."""
    import difflib
    sections = []
    changed_pages = 0
    with open_pdf(before, before_password) as left, open_pdf(after, after_password) as right:
        total = max(len(left), len(right))
        for index in range(total):
            old_lines = left[index].get_text('text').splitlines() if index < len(left) else []
            new_lines = right[index].get_text('text').splitlines() if index < len(right) else []
            diff = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=tr('원본 {page}p', page=index + 1),
                tofile=tr('수정본 {page}p', page=index + 1),
                lineterm='',
            ))
            if diff:
                changed_pages += 1
                sections.append(f'=== {tr("{page}페이지", page=index + 1)} ===\n' + '\n'.join(diff))
    return {
        'changed_pages': changed_pages,
        'total_pages': total,
        'text': '\n\n'.join(sections) if sections else tr('모든 페이지의 추출 텍스트가 동일합니다.'),
    }
