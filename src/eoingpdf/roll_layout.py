"""Vector-preserving vertical page composition for continuous reading."""
from .localization import tr
import math
import pymupdf as pdf
from .core import Cancelled

MAX_ROLL_HEIGHT = 14400


def slice_boundaries(page):
    import numpy as np
    width, height = page.rect.width, page.rect.height
    target_height = width * 842 / 595
    if height <= target_height:
        return [0, height]
    scale = min(1, 512 / width, 16000 / height)
    raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csGRAY, alpha=False)
    pixels = np.frombuffer(raster.samples, dtype=np.uint8).reshape(raster.height, raster.width)
    white = np.all(pixels >= 248, axis=1)
    # Do not mistake whitespace inside a text line or a normal-sized picture for a cut.
    protected = []
    for block in page.get_text('dict', flags=pdf.TEXTFLAGS_DICT & ~pdf.TEXT_PRESERVE_IMAGES)['blocks']:
        if block['type'] == 0:
            protected.extend(pdf.Rect(line['bbox']) * page.rotation_matrix for line in block['lines'])
    for item in page.get_image_info():
        rect = pdf.Rect(item['bbox']) * page.rotation_matrix
        if rect.height <= target_height:
            protected.append(rect)
    for rect in protected:
        first = max(0, int(rect.y0 * raster.height / height) - 1)
        last = min(raster.height, math.ceil(rect.y1 * raster.height / height) + 1)
        white[first:last] = False
    # Require at least three consecutive light scanlines and use the gap center.
    changes = np.diff(np.concatenate(([False], white, [False])).astype(np.int8))
    starts, ends = np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)
    gaps = [(start + end) / 2 * height / raster.height for start, end in zip(starts, ends) if end - start >= 3]
    result = [0.0]
    while height - result[-1] > target_height:
        start = result[-1]
        fitting = [gap for gap in gaps if start + target_height * .25 <= gap <= start + target_height]
        if fitting:
            end = max(fitting)
        else:
            later = [gap for gap in gaps if gap > start + target_height]
            end = min(later) if later else height
        result.append(end)
    if result[-1] < height:
        result.append(height)
    return result


def slice_a4(document, target, cancelled=lambda: False, progress=lambda value: None):
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    document.bake(annots=True, widgets=True)
    with pdf.open() as result:
        for index, source in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            cuts = slice_boundaries(source)
            width = source.rect.width
            rotation, inverse = source.rotation, source.derotation_matrix
            source.set_rotation(0)
            for start, end in zip(cuts, cuts[1:]):
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                page = result.new_page(width=595, height=842)
                scale = min(595 / width, 842 / (end - start))
                left = (595 - width * scale) / 2
                area = pdf.Rect(left, 0, left + width * scale, (end - start) * scale)
                clip = pdf.Rect(0, start, width, end) * inverse
                if source.get_contents():
                    page.show_pdf_page(area, document, index, clip=clip, rotate=-rotation)
            progress(int((index + 1) / len(document) * 90))
        result.save(target, garbage=4, deflate=True)
        return len(result)


def stitch(document, target, cancelled=lambda: False, progress=lambda value: None):
    dimensions = [(page.rect.width, page.rect.height) for page in document]
    if not dimensions or any(not math.isfinite(value) or value <= 0
                             for pair in dimensions for value in pair):
        raise ValueError(tr('연결할 페이지 크기를 확인해 주세요.'))
    # Keep a consistent reading width; scale each source proportionally.
    width = min(1200, max(pair[0] for pair in dimensions))
    heights = [height * width / original_width for original_width, height in dimensions]
    height = sum(heights)
    if height > MAX_ROLL_HEIGHT:
        raise ValueError(tr('연결 결과가 지원 높이 14,400포인트를 초과합니다. 페이지 범위로 문서를 나눈 뒤 연결해 주세요.'))
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    document.bake(annots=True, widgets=True)
    with pdf.open() as result:
        page = result.new_page(width=width, height=height)
        top = 0
        for index, source in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            rotation = source.rotation
            source.set_rotation(0)
            if source.get_contents():
                page.show_pdf_page(pdf.Rect(0, top, width, top + heights[index]), document, index,
                                   clip=source.rect, rotate=-rotation, keep_proportion=True)
            top += heights[index]
            progress(int((index + 1) / len(document) * 90))
        result.set_metadata({'title': tr('세로로 연결한 문서')})
        result.save(target, garbage=4, deflate=True)
    return len(document)
