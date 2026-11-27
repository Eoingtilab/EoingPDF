"""Best-effort removal of invisible text markers and tiny yellow tracking marks."""
from .localization import tr
import re
import pymupdf as pdf
from .core import Cancelled

ZERO_WIDTH = re.compile(r'[\u200b\u200c\u200d\u2060\ufeff]')


def _yellow(fill):
    if not fill or len(fill) < 3:
        return False
    red, green, blue = (float(value) for value in fill[:3])
    return red > .78 and green > .72 and blue < .35


def sanitize(document, cancelled=lambda: False, progress=lambda value: None):
    removed_text = 0
    removed_marks = 0
    for number, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        pending = []
        zero_count = 0
        for block in page.get_text('dict').get('blocks', ()):
            for line in block.get('lines', ()):
                for span in line.get('spans', ()):
                    if ZERO_WIDTH.search(span.get('text', '')):
                        rect = pdf.Rect(span['bbox'])
                        if not rect.is_empty:
                            pending.append((rect, True))
                            zero_count += 1
        for drawing in page.get_drawings():
            rect = pdf.Rect(drawing.get('rect', ()))
            if rect.is_empty or rect.width * rect.height > 144 or not _yellow(drawing.get('fill')):
                continue
            pending.append((rect + (-1, -1, 1, 1), False))
            removed_marks += 1
        removed_text += zero_count
        for rect, white_fill in pending:
            page.add_redact_annot(rect, fill=(1, 1, 1) if white_fill else False)
        if pending:
            page.apply_redactions(images=0, graphics=2, text=0)
        progress(int((number + 1) / len(document) * 90))
    return removed_text, removed_marks


def sanitize_active_content(document, *, remove_scripts=True, remove_attachments=True,
                            cancelled=lambda: False, progress=lambda value: None):
    """Strip JavaScript, launch/open actions, and optionally embedded files."""
    removed = 0
    if remove_attachments:
        for name in list(document.embfile_names()):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            document.embfile_del(name)
            removed += 1
    if remove_scripts:
        for key in ('OpenAction', 'AA', 'JavaScript', 'JS'):
            try:
                catalog = document.pdf_catalog()
                if document.xref_get_key(catalog, key)[0] != 'null':
                    document.xref_set_key(catalog, key, 'null')
                    removed += 1
            except Exception:
                pass
        total = max(1, len(document))
        for index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            for key in ('AA',):
                try:
                    if document.xref_get_key(page.xref, key)[0] != 'null':
                        document.xref_set_key(page.xref, key, 'null')
                        removed += 1
                except Exception:
                    pass
            for annot in list(page.annots() or ()):
                try:
                    info = document.xref_object(annot.xref, compressed=False)
                    if '/JS' in info or '/JavaScript' in info or '/Launch' in info:
                        page.delete_annot(annot)
                        removed += 1
                except Exception:
                    pass
            progress(int((index + 1) / total * 90))
    return removed
