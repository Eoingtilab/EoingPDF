"""Local, page-at-a-time structured Markdown export with explicit extraction limits."""
from .localization import tr
import html
import re
from statistics import median
import pymupdf as pdf
from .core import Cancelled


def escape(text):
    text = html.escape(str(text).replace('\u00a0', ' '), quote=False)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', text)


def table_markdown(rows):
    width = max((len(row) for row in rows), default=0)
    if not rows or not width:
        return ''
    lines = []
    for index, row in enumerate(rows):
        values = [escape(value or '').replace('\r', '').replace('\n', '<br>') for value in row]
        lines.append('| ' + ' | '.join(values + [''] * (width - len(values))) + ' |')
        if index == 0:
            lines.append('| ' + ' | '.join(['---'] * width) + ' |')
    return '\n'.join(lines)


def page_markdown(page):
    blocks = page.get_text('dict', flags=pdf.TEXTFLAGS_DICT & ~pdf.TEXT_PRESERVE_IMAGES, sort=True)['blocks']
    spans = [span for block in blocks if block['type'] == 0
             for line in block['lines'] for span in line['spans'] if span['text'].strip()]
    sizes = [span['size'] for span in spans for _ in range(min(len(span['text']), 100))]
    body_size = median(sizes) if sizes else 12
    pieces, table_rects = [], []
    try:
        finder = page.find_tables()
        for table in finder.tables:
            rows = table.extract()
            if len(rows) >= 2:
                rect = pdf.Rect(table.bbox)
                table_rects.append(rect)
                pieces.append((rect.y0, rect.x0, table_markdown(rows)))
    except Exception:
        pieces.append((-1, 0, tr('> 표 구조를 판독하지 못했습니다. 아래 텍스트와 원문을 확인해 주세요.')))
    for block in blocks:
        if block['type'] != 0:
            continue
        remaining = []
        for line in block['lines']:
            rect = pdf.Rect(line['bbox'])
            if any(rect.intersects(table) and (rect & table).get_area() >= rect.get_area() * .8
                   for table in table_rects):
                continue
            text = ''.join(span['text'] for span in line['spans']).strip()
            if not text:
                continue
            size = max((span['size'] for span in line['spans']), default=body_size)
            if size >= body_size * 1.3:
                level = 2 if size >= body_size * 1.8 else 3
                remaining.append('#' * level + ' ' + escape(text))
            elif re.match(r'^[•●▪]\s*', text):
                remaining.append('- ' + escape(re.sub(r'^[•●▪]\s*', '', text)))
            elif re.match(r'^\d+[.)]\s+', text):
                number, content = re.split(r'[.)]\s+', text, maxsplit=1)
                remaining.append(number + '. ' + escape(content))
            else:
                remaining.append(escape(text))
        if remaining:
            pieces.append((block['bbox'][1], block['bbox'][0], '\n'.join(remaining)))
    if not spans:
        pieces.append((0, 0, tr('> 추출 가능한 텍스트가 없습니다. 스캔 페이지는 OCR 처리 후 다시 내보내 주세요.')))
    if page.get_images():
        pieces.append((float('inf'), 0, tr('> 이 페이지의 이미지는 Markdown에 포함하지 않았습니다. 원본 PDF를 확인해 주세요.')))
    return '\n\n'.join(content for _, _, content in sorted(pieces))


def export(document, target, source_name, cancelled=lambda: False, progress=lambda value: None):
    with open(target, 'w', encoding='utf-8', newline='\n') as output:
        output.write('# ' + escape(source_name) + '\n\n')
        output.write(tr('> PDF에서 로컬로 추출했습니다. 제목·표·읽기 순서는 원문과 확인해 주세요.\n\n'))
        for index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            output.write(tr('<!-- 원본 페이지: {v0} -->\n\n', v0=index + 1))
            output.write(page_markdown(page) + '\n\n---\n\n')
            progress(int((index + 1) / len(document) * 90))
    return len(document)
