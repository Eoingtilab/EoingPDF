"""Persist a presentation's visible-page strokes without replacing any file."""
from .localization import tr
import os
import tempfile
from pathlib import Path

import pymupdf as pdf

from .core import open_pdf
from .ink_stroke import permanent


def save_presentation_ink(source, target, pages, strokes_by_slide, password='', boards=None):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve() or target.exists():
        raise ValueError(tr('원본 또는 기존 파일은 덮어쓸 수 없습니다.'))
    if not pages:
        raise ValueError(tr('저장할 페이지가 없습니다.'))
    boards = boards or {}
    saved_boards = board_order(boards, len(pages))
    descriptor, temporary = tempfile.mkstemp(prefix='.eoing-ink-', suffix='.pdf', dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        with open_pdf(source, password) as document:
            # Preserve the viewer's pending page removal and visible page order.
            document.select(pages)
            for slide, strokes in strokes_by_slide.items():
                if not 0 <= slide < len(pages):
                    raise ValueError(tr('판서 페이지 번호가 올바르지 않습니다.'))
                page = document[slide]
                _write_strokes(page, strokes)
            inserted = 0
            for slide, color in saved_boards:
                board = boards[(slide, color)]
                width, height = board["size"]
                if not (1 <= width <= 14400 and 1 <= height <= 14400):
                    raise ValueError(tr("칠판 크기가 올바르지 않습니다."))
                page = document.new_page(pno=slide + inserted + 1, width=width, height=height)
                background = (0, 0, 0) if color == "black" else (1, 1, 1)
                page.draw_rect(page.rect, color=background, fill=background, overlay=False)
                _write_strokes(page, board["strokes"])
                inserted += 1
            document.save(temporary, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_KEEP)
        with open_pdf(temporary, password) as check:
            if check.page_count != len(pages) + len(saved_boards):
                raise ValueError(tr('저장한 문서의 페이지 수를 확인할 수 없습니다.'))
        # Same-volume hard link publishes only a complete file and refuses a
        # target created by another process after the initial existence check.
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def board_order(boards, count):
    for slide, color in boards:
        if not 0 <= slide < count or color not in ("black", "white"):
            raise ValueError(tr("칠판 페이지 또는 색상이 올바르지 않습니다."))
    return sorted(key for key, board in boards.items()
                  if any(permanent(stroke) for stroke in board["strokes"]))


def _write_strokes(page, strokes):
    for stroke in strokes:
        if not permanent(stroke):
            continue
        points = []
        for point in stroke:
            x, y = float(point.x()), float(point.y())
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError(tr('판서 좌표가 페이지 범위를 벗어났습니다.'))
            mapped = pdf.Point(x * page.rect.width, y * page.rect.height) * page.derotation_matrix
            points.append((mapped.x, mapped.y))
        kind = getattr(stroke, 'kind', '')
        if kind == 'text':
            annotation = page.add_polygon_annot(points)
            annotation.set_border(width=0)
            annotation.set_colors(stroke=None, fill=stroke.color)
            if getattr(stroke, 'text', ''):
                annotation.set_info(content=stroke.text)
        elif kind == 'highlight':
            if len(points) != 4:
                raise ValueError(tr('형광펜 영역이 올바르지 않습니다.'))
            annotation = page.add_highlight_annot(pdf.Quad(points[0], points[1], points[3], points[2]))
        else:
            annotation = page.add_ink_annot([points])
            annotation.set_border(width=getattr(stroke, 'width', 2.5))
        if kind != 'text':
            annotation.set_colors(stroke=getattr(stroke, 'color', (1, .82, 0)))
        annotation.set_opacity(getattr(stroke, 'opacity', .9))
        annotation.update()
