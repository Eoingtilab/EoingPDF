"""Lossless DIB and interoperable UTF-8 CF_HTML / Unicode TSV payloads."""
from .localization import tr
import csv
import html
import io
import math
import re
import time
import pymupdf as pdf


def page_dib(page):
    from PIL import Image
    width = math.ceil(page.rect.width * 300 / 72)
    height = math.ceil(page.rect.height * 300 / 72)
    if width * height > 40_000_000:
        raise ValueError(tr('300DPI 복사가 4천만 픽셀을 초과합니다. 페이지 크기를 줄여 주세요.'))
    pixels = page.get_pixmap(dpi=300, colorspace=pdf.csRGB, alpha=False)
    image = Image.frombytes('RGB', (pixels.width, pixels.height), pixels.samples)
    output = io.BytesIO()
    image.save(output, format='BMP', dpi=(300, 300))
    return output.getvalue()[14:]


def html_clipboard(fragment):
    prefix = b'<html><head><meta charset="utf-8"></head><body><!--StartFragment-->'
    suffix = b'<!--EndFragment--></body></html>'
    content = fragment.encode('utf-8')
    template = 'Version:1.0\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\nStartFragment:{:010d}\r\nEndFragment:{:010d}\r\n'
    start = len(template.format(0, 0, 0, 0).encode('ascii'))
    header = template.format(start, start + len(prefix) + len(content) + len(suffix),
                             start + len(prefix), start + len(prefix) + len(content)).encode('ascii')
    return header + prefix + content + suffix


def safe_cell(value):
    text = str(value if value is not None else '').replace('\x00', '')
    trimmed = text.lstrip()
    if trimmed.startswith(('=', '+', '-', '@')) and not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?', trimmed):
        text = "'" + text
    return text


def table_payload(rows):
    if not rows or sum(len(row) for row in rows) > 100000:
        raise ValueError(tr('복사할 표가 없거나 셀이 10만 개를 초과합니다.'))
    normalized = [[safe_cell(cell) for cell in row] for row in rows]
    output = io.StringIO(newline='')
    csv.writer(output, delimiter='\t', lineterminator='\r\n').writerows(normalized)
    markup = '<table>' + ''.join('<tr>' + ''.join('<td>' + html.escape(cell).replace('\n', '<br>') + '</td>'
                                               for cell in row) + '</tr>' for row in normalized) + '</table>'
    if len(markup) > 16 * 1024 * 1024:
        raise ValueError(tr('복사할 표가 너무 큽니다. 선택 영역을 줄여 주세요.'))
    return output.getvalue(), html_clipboard(markup)


def selection_rect(page, screen_rect, canvas_size):
    width, height = canvas_size
    if min(width, height) <= 0:
        raise ValueError(tr('표시된 페이지가 없습니다.'))
    x0, y0, x1, y1 = screen_rect
    display = pdf.Rect(min(x0, x1) * page.rect.width / width, min(y0, y1) * page.rect.height / height,
                       max(x0, x1) * page.rect.width / width, max(y0, y1) * page.rect.height / height)
    display &= page.rect
    return display * page.derotation_matrix


def extract_table(page, clip):
    if clip.is_empty or clip.width < 5 or clip.height < 5:
        raise ValueError(tr('표 전체를 포함하도록 조금 더 넓게 선택해 주세요.'))
    rotation = page.rotation
    try:
        page.set_rotation(0)
        tables = page.find_tables(clip=clip).tables
        if not tables:
            tables = page.find_tables(clip=clip, strategy='text').tables
        if not tables:
            raise ValueError(tr('선택 영역에서 표를 찾지 못했습니다. 스캔이라면 먼저 검색 가능한 PDF로 변환해 주세요.'))
        table = max(tables, key=lambda item: item.row_count * item.col_count)
        return table.extract()
    finally:
        page.set_rotation(rotation)


def publish(formats, owner):
    import win32clipboard
    import pywintypes
    for attempt in range(5):
        try:
            win32clipboard.OpenClipboard(owner)
            break
        except pywintypes.error:
            if attempt == 4:
                raise ValueError(tr('다른 프로그램이 클립보드를 사용 중입니다. 잠시 후 다시 복사해 주세요.')) from None
            time.sleep(.02)
    try:
        win32clipboard.EmptyClipboard()
        for format_id, value in formats:
            win32clipboard.SetClipboardData(format_id, value)
    finally:
        win32clipboard.CloseClipboard()


def copy_page(page, owner):
    import win32con
    publish([(win32con.CF_DIB, page_dib(page))], owner)


def copy_table(rows, owner):
    import win32clipboard
    import win32con
    tsv, html_data = table_payload(rows)
    html_format = win32clipboard.RegisterClipboardFormat('HTML Format')
    publish([(win32con.CF_UNICODETEXT, tsv), (html_format, html_data)], owner)
