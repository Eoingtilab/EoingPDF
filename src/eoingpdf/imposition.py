"""Vector-preserving A4 print layouts, written as a new PDF."""
from .localization import tr
import pymupdf as pdf
from .core import Cancelled


def sheet_order(count, mode):
    if count < 1:
        raise ValueError(tr('인쇄할 페이지가 없습니다.'))
    if mode == 'four_up':
        return [list(range(start, min(start + 4, count))) for start in range(0, count, 4)]
    if mode != 'booklet':
        raise ValueError(tr('지원하지 않는 인쇄 배치입니다.'))
    padded = ((count + 3) // 4) * 4
    result = []
    for sheet in range(padded // 4):
        for pair in ((padded - 1 - sheet * 2, sheet * 2),
                     (sheet * 2 + 1, padded - 2 - sheet * 2)):
            result.append([index if index < count else None for index in pair])
    return result


def compose(document, target, mode, cancelled=lambda: False, progress=lambda value: None):
    order = sheet_order(len(document), mode)
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    # Include visible annotations/form values in the printable page content.
    document.bake(annots=True, widgets=True)
    width, height = pdf.paper_size('a4-l')
    margin, gap = 18, 12
    rows = 2 if mode == 'four_up' else 1
    cell_width = (width - 2 * margin - gap) / 2
    cell_height = (height - 2 * margin - (rows - 1) * gap) / rows
    with pdf.open() as output:
        for side, sources in enumerate(order):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            page = output.new_page(width=width, height=height)
            for slot, index in enumerate(sources):
                if index is None:
                    continue
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                source = document[index]
                rotation = source.rotation
                source.set_rotation(0)
                x = margin + (slot % 2) * (cell_width + gap)
                y = margin + (slot // 2) * (cell_height + gap)
                if source.get_contents():
                    page.show_pdf_page(pdf.Rect(x, y, x + cell_width, y + cell_height),
                                       document, index, keep_proportion=True, clip=source.rect, rotate=-rotation)
            progress(int((side + 1) / len(order) * 90))
        output.set_metadata({'title': tr('4쪽 모아찍기') if mode == 'four_up' else tr('소책자 인쇄 배치')})
        output.save(target, garbage=4, deflate=True)
    return len(order)
