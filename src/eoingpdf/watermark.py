"""Diagonal embedded-font text and alpha-preserving PNG watermarks."""
from .localization import tr
import io
import math
import uuid
from pathlib import Path
import pymupdf as pdf
from .core import Cancelled


def apply(document, text='', image_path='', opacity=.2, cancelled=lambda: False, progress=lambda value: None):
    if not math.isfinite(opacity) or not .01 <= opacity <= 1:
        raise ValueError(tr('불투명도는 0.01부터 1 사이로 입력해 주세요.'))
    if bool(text.strip()) == bool(image_path):
        raise ValueError(tr('워터마크 문구 또는 PNG 이미지 중 하나를 선택해 주세요.'))
    if len(text) > 200:
        raise ValueError(tr('워터마크 문구는 200자 이하로 입력해 주세요.'))
    stream = None
    if image_path:
        from PIL import Image
        path = Path(image_path)
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError(tr('20MB 이하의 PNG 파일을 선택해 주세요.'))
        with Image.open(path) as image:
            if image.format != 'PNG' or image.width * image.height > 40_000_000:
                raise ValueError(tr('4천만 픽셀 이하의 PNG 이미지를 선택해 주세요.'))
            image = image.convert('RGBA')
            image.putalpha(image.getchannel('A').point(lambda value: round(value * opacity)))
            aspect = image.width / image.height
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            stream = buffer.getvalue()
    else:
        from .pdf_fonts import text_font
        font = text_font(text)
        font_name = 'EoingWM' + uuid.uuid4().hex
        text = ' '.join(text.split())
    for index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        rect = page.rect
        center = (rect.tl + rect.br) / 2
        if stream:
            width = min(rect.width * .65, rect.height * .65 * aspect)
            height = width / aspect
            area = pdf.Rect(center.x - width / 2, center.y - height / 2,
                            center.x + width / 2, center.y + height / 2)
            raw_area = area * page.derotation_matrix
            rotation = page.rotation
            page.set_rotation(0)
            try:
                page.insert_image(raw_area, stream=stream, rotate=rotation, overlay=True)
            finally:
                page.set_rotation(rotation)
        else:
            page.insert_font(fontname=font_name, fontbuffer=font.buffer)
            size = min(48, min(rect.width, rect.height) * .85 / max(font.text_length(text, fontsize=1), .01))
            width = font.text_length(text, fontsize=size)
            baseline = pdf.Point(center.x - width / 2, center.y + size * (font.ascender + font.descender) / 2)
            raw_center = center * page.derotation_matrix
            raw_baseline = raw_center + (baseline - center)
            page.insert_text(raw_baseline, text, fontname=font_name, fontsize=size, color=(.22, .28, .4),
                             fill_opacity=opacity, morph=(raw_center,
                                                          pdf.Matrix(45 + page.rotation)), overlay=True)
        progress(int((index + 1) / len(document) * 90))
    return len(document)
