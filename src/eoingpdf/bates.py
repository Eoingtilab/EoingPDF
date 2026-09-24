"""Bates labels and a clickable single-page contents cover."""
from .localization import tr
import re
import pymupdf as pdf
from .core import Cancelled
from .pdf_fonts import text_font


def apply(document, prefix='', start=1, digits=6, hide_old=True, cover=False,
          cancelled=lambda: False, progress=lambda value: None):
    if not isinstance(prefix, str) or len(prefix) > 40 or any(ord(char) < 32 for char in prefix):
        raise ValueError(tr('번호 접두어는 줄바꿈 없이 40자 이하로 입력해 주세요.'))
    if type(start) is not int or not 1 <= start <= 999999999 or type(digits) is not int or not 1 <= digits <= 12:
        raise ValueError(tr('시작 번호 또는 자리 수를 확인해 주세요.'))
    toc = document.get_toc()
    entries = [entry for entry in toc if entry[0] == 1 and 1 <= entry[2] <= len(document)]
    if cover and not entries:
        entries = [[1, tr('문서'), 1]]
    if cover and len(entries) > 40:
        raise ValueError(tr('한 장 목차 표지는 최대 40개 문서까지 지원합니다.'))
    heading = tr('문서 목차')
    font = text_font(prefix, heading if cover else '', *(entry[1] for entry in entries if cover))
    count = len(document)
    for index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        rect = page.rect
        if hide_old:
            old_number_boxes = []
            for block in page.get_text('dict', flags=pdf.TEXTFLAGS_DICT & ~pdf.TEXT_PRESERVE_IMAGES)['blocks']:
                if block['type'] != 0:
                    continue
                for line in block['lines']:
                    text = ''.join(span['text'] for span in line['spans']).strip()
                    box = pdf.Rect(line['bbox'])
                    shown = box * page.rotation_matrix
                    if shown.y0 >= rect.height * .9 and re.fullmatch(r'(?:[Pp]age\s*)?\d{1,6}(?:\s*/\s*\d{1,6})?', text):
                        old_number_boxes.append(box + (-1, -1, 1, 1))
            for box in old_number_boxes:
                page.add_redact_annot(box, fill=(1, 1, 1))
            if old_number_boxes:
                page.apply_redactions(images=0, graphics=0, text=0)
        label = prefix + str(start + index).zfill(digits)
        size = min(10, max(1, rect.width - 24) / max(font.text_length(label, fontsize=1), .01))
        width = font.text_length(label, fontsize=size)
        shown = pdf.Point((rect.width - width) / 2, rect.height - 12)
        point = shown * page.derotation_matrix
        page.insert_font(fontname='EoingBates', fontbuffer=font.buffer)
        page.insert_text(point, label, fontname='EoingBates', fontsize=size,
                         morph=(point, pdf.Matrix(page.rotation)), overlay=True)
        progress(int((index + 1) / count * 80))
    if cover:
        page = document.new_page(pno=0, width=595, height=842)
        page.insert_font(fontname='EoingBates', fontbuffer=font.buffer)
        page.insert_text((40, 60), heading, fontname='EoingBates', fontsize=24)
        for index, (_, title, number) in enumerate(entries):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            text = f'{index + 1}. {title}  ·  {prefix}{str(start + number - 1).zfill(digits)}'
            size = min(12, 515 / max(font.text_length(text, fontsize=1), .01))
            y = 100 + index * 17
            page.insert_text((40, y), text, fontname='EoingBates', fontsize=size)
            page.insert_link({'kind': pdf.LINK_GOTO, 'from': pdf.Rect(38, y - 14, 558, y + 3),
                              'page': number, 'to': pdf.Point(0, 0)})
        document.set_toc([[level, title, number + 1 if number > 0 else number] for level, title, number in toc])
    return count
