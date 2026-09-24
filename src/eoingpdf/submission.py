"""Correct scans and physically remove recognized personal data from a new PDF."""
from .localization import tr
import io
import math
import re

import pymupdf as pdf

from .core import Cancelled


def sensitive_regions(layout, page):
    from .advanced import sensitive_matches
    width, height = float(layout['width']), float(layout['height'])
    if not math.isfinite(width) or not math.isfinite(height) or min(width, height) <= 0:
        raise ValueError(tr('글자 인식 좌표를 읽을 수 없습니다.'))
    rectangles = set()
    for line in layout['lines']:
        words = []
        for word in line['words']:
            text = word['text']
            x, y, w, h = map(float, word['box'])
            if not all(math.isfinite(n) for n in (x, y, w, h)) or min(w, h) <= 0:
                raise ValueError(tr('글자 인식 좌표를 읽을 수 없습니다.'))
            if text.strip():
                words.append((text, (x, y, x + w, y + h)))
        # OCR can split a phone number or email into separate tokens.
        for separator in (' ', ''):
            joined, spans = '', []
            for text, box in words:
                if joined:
                    joined += separator
                start = len(joined)
                joined += text
                spans.append((start, len(joined), box))
            for match in sensitive_matches(joined):
                for occurrence in re.finditer(re.escape(match), joined):
                    for start, end, box in spans:
                        if start < occurrence.end() and end > occurrence.start():
                            rect = pdf.Rect(box)
                            rect = pdf.Rect(rect.x0 / width * page.rect.width,
                                            rect.y0 / height * page.rect.height,
                                            rect.x1 / width * page.rect.width,
                                            rect.y1 / height * page.rect.height)
                            rect = (rect + (-1, -1, 1, 1)) & page.rect
                            if not rect.is_empty:
                                rectangles.add(tuple(rect))
    return rectangles


def prepare(document, target, cancelled, progress):
    import numpy as np
    from PIL import Image
    from .advanced import sensitive_matches
    from .imaging import deskew, remove_shadows
    from .ocr import page_layout

    changed = 0
    with pdf.open() as output:
        for index, source in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            # Remove native text before rasterization, independently of OCR quality.
            native = {tuple(rect) for match in sensitive_matches(source.get_text())
                      for rect in source.search_for(match)}
            for rect in native:
                source.add_redact_annot(pdf.Rect(rect), fill=(0, 0, 0))
            if native:
                source.apply_redactions(images=2, graphics=0, text=0)
            changed += len(native)
            width, height = math.ceil(source.rect.width * 300 / 72), math.ceil(source.rect.height * 300 / 72)
            if width * height > 40_000_000:
                raise ValueError(tr('300DPI 출력이 4천만 픽셀을 초과하는 페이지입니다. 용지 크기를 줄여 주세요.'))
            raster = source.get_pixmap(dpi=300, colorspace=pdf.csRGB, alpha=False, annots=True)
            pixels = np.frombuffer(raster.samples, dtype=np.uint8).reshape(raster.height, raster.width, 3)
            corrected = remove_shadows(deskew(pixels).image)
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            buffer = io.BytesIO()
            Image.fromarray(corrected).save(buffer, format='PNG')
            page = output.new_page(width=corrected.shape[1] * 72 / 300, height=corrected.shape[0] * 72 / 300)
            page.insert_image(page.rect, stream=buffer.getvalue())
            rectangles = sensitive_regions(page_layout(page, cancelled), page)
            for rect in rectangles:
                page.add_redact_annot(pdf.Rect(rect), fill=(0, 0, 0))
            if rectangles:
                page.apply_redactions(images=2, graphics=0, text=0)
            changed += len(rectangles)
            progress(int((index + 1) / len(document) * 90))
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        # This new document has no original metadata, hidden text, or attachments.
        output.save(target, garbage=4, deflate=True)
    return changed
