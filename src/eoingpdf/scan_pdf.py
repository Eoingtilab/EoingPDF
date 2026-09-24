"""Page-at-a-time 300 DPI lossless raster output with a pixel allocation limit."""
from .localization import tr
import io
import math
import pymupdf as pdf
from .core import Cancelled


def render_copy(document, target, operation, cancelled, progress):
    import numpy as np
    with pdf.open() as output:
        for index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            width, height = math.ceil(page.rect.width * 300 / 72), math.ceil(page.rect.height * 300 / 72)
            if width * height > 40_000_000:
                raise ValueError(tr('300DPI 출력이 4천만 픽셀을 초과하는 페이지입니다. 용지 크기를 줄여 주세요.'))
            pixmap = page.get_pixmap(dpi=300, colorspace=pdf.csRGB, alpha=False, annots=True)
            if operation == 'flatten':
                stream = pixmap.tobytes('png')
                size = page.rect.width, page.rect.height
            elif operation in {'smart_dark', 'print_light'}:
                pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3).copy()
                preserve = np.zeros((pixmap.height, pixmap.width), dtype=bool)
                scale_x = pixmap.width / max(page.rect.width, 1)
                scale_y = pixmap.height / max(page.rect.height, 1)
                for info in page.get_image_info(xrefs=True):
                    rect = pdf.Rect(info['bbox']) * page.rotation_matrix
                    left = max(0, math.floor(rect.x0 * scale_x))
                    top = max(0, math.floor(rect.y0 * scale_y))
                    right = min(pixmap.width, math.ceil(rect.x1 * scale_x))
                    bottom = min(pixmap.height, math.ceil(rect.y1 * scale_y))
                    if right > left and bottom > top:
                        preserve[top:bottom, left:right] = True
                if operation == 'smart_dark':
                    pixels[~preserve] = 255 - pixels[~preserve]
                else:
                    # Only change predominantly dark pages. Colored vector
                    # artwork and raster image rectangles retain their colors.
                    neutral = pixels.max(axis=2).astype(np.int16) - pixels.min(axis=2) <= 35
                    dark = pixels.max(axis=2) < 90
                    background = ~preserve
                    area = int(background.sum())
                    if area and int((dark & neutral & background).sum()) / area >= .7:
                        modify = neutral & background
                        light = pixels.min(axis=2) >= 160
                        pixels[modify] = 255 - pixels[modify]
                        pixels[modify & dark] = 255
                        pixels[modify & light] = 0
                from PIL import Image
                buffer = io.BytesIO()
                Image.fromarray(pixels).save(buffer, format='PNG')
                stream = buffer.getvalue()
                size = page.rect.width, page.rect.height
            else:
                from PIL import Image
                from .imaging import deskew
                pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
                corrected = deskew(pixels, monochrome=operation == 'deskew_bw')
                buffer = io.BytesIO()
                Image.fromarray(corrected.image).save(buffer, format='PNG')
                stream = buffer.getvalue()
                size = corrected.image.shape[1] * 72 / 300, corrected.image.shape[0] * 72 / 300
            new_page = output.new_page(width=size[0], height=size[1])
            new_page.insert_image(new_page.rect, stream=stream)
            progress(int((index + 1) / len(document) * 90))
        output.save(target, garbage=4, deflate=True)
        return len(output)
