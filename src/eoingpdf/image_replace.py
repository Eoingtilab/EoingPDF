"""Replace repeated raster logos by decoded pixel identity, retaining placement."""
from .localization import tr
import hashlib
import io
from pathlib import Path
import pymupdf as pdf
from .core import Cancelled


def decoded(document, xref, mask=0):
    width = int(document.xref_get_key(xref, 'Width')[1])
    height = int(document.xref_get_key(xref, 'Height')[1])
    if width * height > 40_000_000:
        raise ValueError(tr('4천만 픽셀을 초과하는 문서 이미지입니다.'))
    raster = pdf.Pixmap(document, xref)
    if raster.colorspace is None:
        raise ValueError(tr('독립된 색상 이미지가 아닙니다.'))
    if raster.colorspace.n != 3:
        raster = pdf.Pixmap(pdf.csRGB, raster)
    if mask:
        raster = pdf.Pixmap(raster, pdf.Pixmap(document, mask))
    digest = hashlib.sha256(f'{raster.width}:{raster.height}:{raster.n}:'.encode() + raster.samples).hexdigest()
    return raster, digest


def inventory(document, cancelled=lambda: False, progress=lambda value: None):
    images = {}
    for number, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        visible = {entry['xref'] for entry in page.get_image_info(xrefs=True) if entry['xref']}
        for entry in page.get_images(full=True):
            xref, mask = entry[:2]
            if xref not in visible:
                continue
            if xref in images:
                images[xref]['pages'].add(number)
                continue
            if len(images) >= 1000:
                raise ValueError(tr('이미지가 1000개를 초과합니다. 문서를 나눠서 처리해 주세요.'))
            raster, digest = decoded(document, xref, mask)
            width, height = raster.width, raster.height
            while max(raster.width, raster.height) > 180:
                raster.shrink(1)
            images[xref] = dict(xref=xref, digest=digest, width=width, height=height,
                                pages={number}, preview=raster.tobytes('png'))
        progress(int((number + 1) / len(document) * 45))
    return list(images.values())


def replacement(path, aspect):
    from PIL import Image, ImageOps
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError(tr('20MB 이하의 PNG 또는 JPEG를 선택해 주세요.'))
    with Image.open(path) as source:
        if source.format not in {'PNG', 'JPEG'} or source.width * source.height > 40_000_000:
            raise ValueError(tr('4천만 픽셀 이하의 PNG 또는 JPEG를 선택해 주세요.'))
        image = ImageOps.exif_transpose(source).convert('RGBA')
    # Contain without enlarging the new image; transparent padding preserves its aspect.
    width = max(image.width, round(image.height * aspect))
    height = max(image.height, round(image.width / aspect))
    if width * height > 40_000_000:
        raise ValueError(tr('원래 이미지 비율에 맞춘 결과가 너무 큽니다. 새 이미지를 줄여 주세요.'))
    canvas = Image.new('RGBA', (width, height))
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    output = io.BytesIO()
    canvas.save(output, format='PNG')
    return output.getvalue()


def apply(document, xref, image_path, expected_digest='', cancelled=lambda: False, progress=lambda value: None):
    candidates = inventory(document, cancelled, progress)
    chosen = next((item for item in candidates if item['xref'] == xref), None)
    if chosen is None:
        raise ValueError(tr('교체할 이미지를 문서에서 다시 선택해 주세요.'))
    if expected_digest and chosen['digest'] != expected_digest:
        raise ValueError(tr('이미지를 선택한 뒤 원본이 변경되었습니다. 다시 선택해 주세요.'))
    matching = [item for item in candidates if item['digest'] == chosen['digest']]
    stream = replacement(image_path, chosen['width'] / chosen['height'])
    for index, item in enumerate(matching):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        document[min(item['pages'])].replace_image(item['xref'], stream=stream)
        progress(45 + int((index + 1) / len(matching) * 45))
    return len(matching)
