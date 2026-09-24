"""Read native text and locally recognize scanned content with PDF coordinates."""
from .localization import tr
import math


def page_blocks(page, use_ocr=False, cancelled=lambda: False):
    blocks = [block for block in page.get_text('blocks') if block[6] == 0 and block[4].strip()]
    if not use_ocr:
        return blocks
    import pymupdf as pdf
    visible = page.rect * page.derotation_matrix
    if not any(pdf.Rect(image['bbox']).intersects(visible) for image in page.get_image_info()):
        return blocks
    from .ocr import page_layout
    from .core import Cancelled
    from .semantic_search import SearchCancelled
    try:
        layout = page_layout(page, cancelled)
    except Cancelled as error:
        raise SearchCancelled() from error
    sx, sy = page.rect.width / layout['width'], page.rect.height / layout['height']
    result = list(blocks)
    native_rects = [pdf.Rect(word[:4]) for word in page.get_text('words')]
    for line in layout['lines']:
        if cancelled():
            raise SearchCancelled()
        rectangle = pdf.Rect()
        texts = []
        for word in line.get('words', []):
            box = word.get('box', [])
            if len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box):
                raise ValueError(tr('OCR 검색 좌표가 올바르지 않습니다.'))
            x, y, width, height = box
            if width > 0 and height > 0:
                word_rect = pdf.Rect(x * sx, y * sy, (x + width) * sx, (y + height) * sy) & page.rect
                word_rect = word_rect * page.derotation_matrix
                if word_rect.is_empty:
                    continue
                if any((word_rect & native).get_area() >= word_rect.get_area() * .6 for native in native_rects):
                    continue
                text = word.get('text', '').strip()
                if text:
                    texts.append(text)
                    rectangle |= word_rect
        text = ' '.join(texts)
        if text and not rectangle.is_empty:
            result.append((*rectangle, text, len(result), 0))
    return result
