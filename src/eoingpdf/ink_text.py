"""Pretendard glyph outlines for live text and portable PDF vector annotations."""
from .localization import tr
from functools import lru_cache
from pathlib import Path
import sys

from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QFontDatabase, QPainterPath, QTextLayout, QTextOption

from .ink_stroke import InkStroke


@lru_cache(maxsize=1)
def text_family():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    identifier = QFontDatabase.addApplicationFont(str(root / 'assets/fonts/Pretendard-Regular.ttf'))
    families = QFontDatabase.applicationFontFamilies(identifier)
    if not families:
        raise ValueError(tr('프리텐다드 글꼴을 불러올 수 없습니다.'))
    return families[0]


def text_strokes(text, anchor, page_size, color, font_size=18):
    text = text.strip()
    if not text:
        return []
    if len(text) > 256:
        raise ValueError(tr('텍스트는 한 번에 256자까지 입력할 수 있습니다.'))
    width, height = page_size
    x, y = anchor.x() * width, anchor.y() * height
    available = width - x - 2
    if available < font_size or height - y < font_size:
        raise ValueError(tr('글자를 넣을 공간이 부족합니다. 페이지 안쪽을 선택해 주세요.'))
    font = QFont(text_family())
    font.setPixelSize(font_size)
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    path, offset = QPainterPath(), 0.0
    utf16 = text.encode('utf-16-le')
    try:
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(available)
            if y + offset + line.height() > height - 2:
                raise ValueError(tr('텍스트가 페이지를 벗어납니다. 내용을 줄여 주세요.'))
            path.addText(QPointF(x, y + offset + line.ascent()), font,
                         utf16[line.textStart() * 2:(line.textStart() + line.textLength()) * 2].decode('utf-16-le'))
            offset += line.height()
    finally:
        layout.endLayout()
    result = []
    for polygon in path.toFillPolygons():
        points = [QPointF(point.x() / width, point.y() / height) for point in polygon]
        if any(not (0 <= point.x() <= 1 and 0 <= point.y() <= 1) for point in points):
            raise ValueError(tr('글자 윤곽이 페이지를 벗어납니다. 안쪽에 입력해 주세요.'))
        if len(points) >= 3:
            stroke = InkStroke(points, 'text')
            stroke.color, stroke.opacity, stroke.fill = color, 1.0, True
            stroke.text = text if not result else ''
            result.append(stroke)
    return result
