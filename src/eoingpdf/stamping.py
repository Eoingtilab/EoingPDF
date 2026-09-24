"""White-background knockout and display-coordinate stamp placement."""
from .localization import tr
import io
import math
from pathlib import Path
import pymupdf as pdf
from .core import Cancelled, pages_from_text


def prepare_image(path):
    from PIL import Image, ImageOps
    import numpy as np
    from .imaging import knockout_white
    path = Path(path)
    if path.suffix.lower() == '.eoseal':
        from .seal_vault import read_seal
        _, stream = read_seal(path)
        with Image.open(io.BytesIO(stream)) as image:
            return stream, image.width / image.height
    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError(tr('20MB 이하의 도장·서명 이미지를 선택해 주세요.'))
    with Image.open(path) as source:
        if source.format not in {'PNG', 'JPEG'} or source.width * source.height > 40_000_000:
            raise ValueError(tr('4천만 픽셀 이하의 PNG 또는 JPEG를 선택해 주세요.'))
        image = ImageOps.exif_transpose(source).convert('RGBA')
        image = Image.fromarray(knockout_white(np.asarray(image)))
    bounds = image.getchannel('A').getbbox()
    if bounds is None:
        raise ValueError(tr('흰 배경을 제거한 뒤 남는 도장·서명이 없습니다.'))
    image = image.crop(bounds)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue(), image.width / image.height


def apply(document, image_path, pages='1', x_mm=10, y_mm=10, width_mm=30,
          cancelled=lambda: False, progress=lambda value: None):
    values = (x_mm, y_mm, width_mm)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in values) or min(x_mm, y_mm) < 0 or not 1 <= width_mm <= 1000:
        raise ValueError(tr('위치는 0 이상, 너비는 1~1000mm로 입력해 주세요.'))
    selected = list(range(len(document))) if not str(pages).strip() else list(dict.fromkeys(pages_from_text(pages, len(document))))
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    stream, aspect = prepare_image(image_path)
    unit = 72 / 25.4
    width, height = width_mm * unit, width_mm * unit / aspect
    area = pdf.Rect(x_mm * unit, y_mm * unit, x_mm * unit + width, y_mm * unit + height)
    for index in selected:
        if not document[index].rect.contains(area):
            raise ValueError(tr('{v0}페이지 밖으로 도장이 나갑니다. 위치나 크기를 줄여 주세요.', v0=index + 1))
    for step, index in enumerate(selected):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        page = document[index]
        raw_area = area * page.derotation_matrix
        rotation = page.rotation
        page.set_rotation(0)
        try:
            page.insert_image(raw_area, stream=stream, rotate=rotation, overlay=True)
        finally:
            page.set_rotation(rotation)
        progress(int((step + 1) / len(selected) * 45))
    return len(selected)
