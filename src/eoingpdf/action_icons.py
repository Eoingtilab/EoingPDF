"""One scalable, palette-aware line icon family for PDF actions.

No emoji, image files, font glyphs, raster cache or theme signal connections.
Icons bound to a button use its current palette, including the presentation's
fixed dark controls when the rest of the application uses the light theme.
"""
import math
import weakref

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QMenu
from shiboken6 import isValid


ICON_NAMES = (
    'open', 'play', 'stamp', 'tools', 'save', 'close', 'undo', 'redo',
    'history', 'form', 'pages', 'copy', 'table', 'list', 'thumbnail',
    'rename', 'delete', 'up', 'down', 'previous', 'next', 'print',
    'settings', 'license', 'update', 'restore', 'reset', 'image',
    'vault', 'pen', 'highlight', 'eraser', 'select', 'line',
    'rectangle', 'ellipse', 'arrow', 'text', 'color', 'capture',
    'clear', 'presenter', 'fit', 'scan', 'security', 'unlock',
    'export', 'optimize', 'search', 'watermark',
)
_ALIASES = {'erase': 'eraser', 'paste': 'copy', 'shape': 'rectangle',
            'ghost': 'pen', 'presentation': 'play', 'slideshow': 'play',
            'lock': 'security', 'repair': 'restore', 'compress': 'optimize',
            'revert': 'reset', 'fill': 'color', 'font': 'text'}
_CATEGORY_ICONS = {'edit': 'stamp', 'pages': 'pages', 'scan': 'scan',
                   'security': 'security', 'view': 'presenter',
                   'export': 'export', 'optimize': 'optimize'}
_TOOL_ICONS = {
    'presentation': 'play', 'stamp': 'stamp', 'form': 'form',
    'auto_forms': 'form', 'watermark_text': 'watermark', 'watermark_png': 'image',
    'replace_image': 'image', 'bates': 'list', 'reverse': 'pages',
    'remove_blank': 'delete', 'trim': 'fit', 'split_spread': 'pages',
    'split_ranges': 'pages', 'split_groups': 'pages', 'split_toc': 'list',
    'stitch': 'pages', 'slice_a4': 'pages', 'deskew': 'scan',
    'deskew_bw': 'scan', 'searchable': 'search', 'safe_submission': 'security',
    'ocr_redact': 'security', 'encrypt': 'security', 'decrypt': 'unlock',
    'redact': 'security', 'metadata': 'clear', 'smart_dark': 'presenter',
    'print_light': 'print', 'flatten': 'image', 'four_up': 'thumbnail',
    'booklet': 'pages', 'outlines': 'text', 'markdown': 'export',
    'dxf': 'export', 'svg': 'export', 'target_size': 'optimize', 'repair': 'restore',
    'table': 'table', 'copy_image': 'copy', 'viewmode': 'thumbnail',
}


def _canonical(name):
    name = _ALIASES.get(str(name), str(name))
    return name if name in ICON_NAMES else 'tools'


def _polyline(painter, *points):
    painter.drawPolyline(QPolygonF([QPointF(*point) for point in points]))


def _polygon(painter, *points):
    painter.drawPolygon(QPolygonF([QPointF(*point) for point in points]))


def _document(painter, x=3, y=2, width=10, height=12):
    _polygon(painter, (x, y), (x + width - 3, y), (x + width, y + 3),
             (x + width, y + height), (x, y + height))
    _polyline(painter, (x + width - 3, y), (x + width - 3, y + 3), (x + width, y + 3))


def _curve(painter, points):
    path = QPainterPath(QPointF(*points[0]))
    path.cubicTo(*(QPointF(*point) for point in points[1:]))
    painter.drawPath(path)


def _draw_symbol(painter, name):
    """Draw on a 16 point grid; every symbol uses the same 1.4 point pen."""
    if name == 'open':
        _polyline(painter, (2, 6), (2, 3.5), (6, 3.5), (7.5, 5), (13, 5), (13, 7))
        _polygon(painter, (2, 7), (14, 7), (12.5, 12.5), (2, 12.5))
    elif name == 'play':
        _polygon(painter, (5, 2.5), (13, 8), (5, 13.5))
    elif name == 'stamp':
        painter.drawRoundedRect(QRectF(2.5, 10.5, 11, 3), .6, .6)
        _polyline(painter, (5.5, 10.5), (6, 6.5), (5, 4.5), (6, 2.5),
                  (10, 2.5), (11, 4.5), (10, 6.5), (10.5, 10.5))
    elif name in ('tools', 'thumbnail'):
        for x, y in ((2.5, 2.5), (9.5, 2.5), (2.5, 9.5), (9.5, 9.5)):
            painter.drawRoundedRect(QRectF(x, y, 4, 4), .6, .6)
    elif name == 'save':
        _polygon(painter, (2.5, 2.5), (11, 2.5), (13.5, 5), (13.5, 13.5), (2.5, 13.5))
        _polyline(painter, (5, 2.5), (5, 6), (10, 6), (10, 2.5))
        painter.drawRect(QRectF(5, 9, 6, 4.5))
    elif name == 'close':
        _polyline(painter, (4, 4), (12, 12))
        _polyline(painter, (12, 4), (4, 12))
    elif name in ('undo', 'redo'):
        if name == 'redo':
            painter.translate(16, 0)
            painter.scale(-1, 1)
        _polyline(painter, (5.5, 2.5), (2.5, 5.5), (5.5, 8.5))
        _curve(painter, ((2.5, 5.5), (14.5, 3.5), (15, 13), (8.5, 13)))
    elif name in ('history', 'restore', 'reset', 'update'):
        _polyline(painter, (2.5, 3.5), (2.5, 7), (6, 7))
        painter.drawArc(QRectF(2.5, 2.5, 11, 11), 145 * 16, -300 * 16)
        if name == 'history':
            _polyline(painter, (8, 4.5), (8, 8), (10.5, 9.5))
        elif name == 'restore':
            _polyline(painter, (5.5, 9), (7.5, 11), (11, 7.5))
        elif name == 'update':
            _polyline(painter, (5.5, 8), (8, 5.5), (10.5, 8))
            _polyline(painter, (8, 5.5), (8, 11.5))
    elif name == 'form':
        _document(painter)
        _polyline(painter, (5, 6), (8, 6))
        painter.drawRect(QRectF(5, 9, 6, 2.5))
    elif name == 'pages':
        _polyline(painter, (3, 11.5), (2, 11.5), (2, 2), (10, 2), (10, 3.5))
        painter.drawRoundedRect(QRectF(5, 4.5, 8.5, 9), .6, .6)
    elif name == 'copy':
        _polyline(painter, (3.5, 10.5), (2, 10.5), (2, 2), (10.5, 2), (10.5, 3.5))
        painter.drawRoundedRect(QRectF(5.5, 5.5, 8, 8), .6, .6)
    elif name == 'table':
        painter.drawRoundedRect(QRectF(2.5, 2.5, 11, 11), .6, .6)
        _polyline(painter, (2.5, 6.5), (13.5, 6.5))
        _polyline(painter, (2.5, 10), (13.5, 10))
        _polyline(painter, (6.5, 2.5), (6.5, 13.5))
    elif name == 'list':
        for y in (3.5, 8, 12.5):
            _polyline(painter, (2.5, y), (3.5, y))
            _polyline(painter, (6.5, y), (13.5, y))
    elif name in ('rename', 'pen', 'highlight'):
        _polygon(painter, (3, 10), (10.5, 2.5), (13.5, 5.5), (6, 13), (2.5, 13.5))
        _polyline(painter, (8.5, 4.5), (11.5, 7.5))
        if name == 'highlight':
            _polyline(painter, (8.5, 13.5), (13.5, 13.5))
        elif name == 'rename':
            _polyline(painter, (2.5, 2.5), (6, 2.5))
    elif name == 'delete':
        _polyline(painter, (2.5, 4.5), (13.5, 4.5))
        _polyline(painter, (5.5, 4.5), (5.5, 2.5), (10.5, 2.5), (10.5, 4.5))
        _polyline(painter, (4, 4.5), (4.5, 13.5), (11.5, 13.5), (12, 4.5))
        _polyline(painter, (6.5, 7), (6.5, 11))
        _polyline(painter, (9.5, 7), (9.5, 11))
    elif name in ('up', 'down', 'previous', 'next'):
        if name == 'up':
            _polyline(painter, (3.5, 10), (8, 5.5), (12.5, 10))
        elif name == 'down':
            _polyline(painter, (3.5, 6), (8, 10.5), (12.5, 6))
        elif name == 'previous':
            _polyline(painter, (10, 3.5), (5.5, 8), (10, 12.5))
        else:
            _polyline(painter, (6, 3.5), (10.5, 8), (6, 12.5))
    elif name == 'print':
        _polyline(painter, (5, 5.5), (5, 2.5), (11, 2.5), (11, 5.5))
        _polyline(painter, (4.5, 11), (2.5, 11), (2.5, 5.5), (13.5, 5.5), (13.5, 11), (11.5, 11))
        painter.drawRect(QRectF(5, 9, 6, 4.5))
        _polyline(painter, (10.5, 7.5), (11, 7.5))
    elif name == 'settings':
        for y, position in ((3.5, 6), (8, 10), (12.5, 5)):
            _polyline(painter, (2.5, y), (position - 1.5, y))
            _polyline(painter, (position + 1.5, y), (13.5, y))
            painter.drawEllipse(QRectF(position - 1.5, y - 1.5, 3, 3))
    elif name == 'license':
        painter.drawRoundedRect(QRectF(2.5, 3.5, 11, 9), .7, .7)
        painter.drawEllipse(QRectF(4.5, 5.5, 3, 3))
        _polyline(painter, (4.5, 10.5), (7.5, 10.5))
        _polyline(painter, (9.5, 6), (11.5, 6))
        _polyline(painter, (9.5, 9), (11.5, 9))
    elif name == 'image':
        painter.drawRoundedRect(QRectF(2.5, 2.5, 11, 11), .7, .7)
        painter.drawEllipse(QRectF(5, 4.5, 2, 2))
        _polyline(painter, (2.5, 11), (6.5, 8), (9, 10), (11, 7.5), (13.5, 10))
    elif name == 'vault':
        painter.drawRoundedRect(QRectF(2.5, 2.5, 11, 11), 1, 1)
        painter.drawEllipse(QRectF(5.5, 5.5, 5, 5))
        _polyline(painter, (8, 5.5), (8, 10.5))
        _polyline(painter, (5.5, 8), (10.5, 8))
    elif name == 'eraser':
        _polygon(painter, (2.5, 9.5), (8.5, 2.5), (13.5, 7), (8, 13.5), (6, 13.5))
        _polyline(painter, (5.5, 6), (10.5, 10.5))
        _polyline(painter, (8, 13.5), (13.5, 13.5))
    elif name == 'select':
        _polygon(painter, (3, 2.5), (12.5, 8.5), (8.5, 9), (6.5, 13.5))
        _polyline(painter, (8.5, 9), (11.5, 13))
    elif name in ('line', 'arrow'):
        _polyline(painter, (2.5, 13.5), (13.5, 2.5))
        if name == 'arrow':
            _polyline(painter, (6.5, 2.5), (13.5, 2.5), (13.5, 9.5))
    elif name == 'rectangle':
        painter.drawRect(QRectF(2.5, 3.5, 11, 9))
    elif name == 'ellipse':
        painter.drawEllipse(QRectF(2.5, 3.5, 11, 9))
    elif name in ('text', 'watermark'):
        _polyline(painter, (3, 3), (13, 3))
        _polyline(painter, (8, 3), (8, 13))
        _polyline(painter, (5.5, 13), (10.5, 13))
        if name == 'watermark':
            _polyline(painter, (2.5, 11), (13.5, 6))
    elif name == 'color':
        painter.drawEllipse(QRectF(2.5, 2.5, 11, 11))
        for x, y in ((6, 5), (10, 5), (11, 9), (5, 9)):
            painter.drawEllipse(QRectF(x - .7, y - .7, 1.4, 1.4))
    elif name in ('capture', 'scan', 'fit'):
        for points in (((5.5, 2.5), (2.5, 2.5), (2.5, 5.5)),
                       ((10.5, 2.5), (13.5, 2.5), (13.5, 5.5)),
                       ((2.5, 10.5), (2.5, 13.5), (5.5, 13.5)),
                       ((10.5, 13.5), (13.5, 13.5), (13.5, 10.5))):
            _polyline(painter, *points)
        if name == 'capture':
            painter.drawEllipse(QRectF(5.5, 5.5, 5, 5))
        elif name == 'scan':
            _polyline(painter, (5.5, 6), (10.5, 6))
            _polyline(painter, (5.5, 10), (10.5, 10))
        else:
            _polyline(painter, (6, 6), (10, 10))
            _polyline(painter, (6, 8.5), (6, 6), (8.5, 6))
            _polyline(painter, (7.5, 10), (10, 10), (10, 7.5))
    elif name == 'clear':
        _document(painter)
        _polyline(painter, (5.5, 7), (10.5, 12))
        _polyline(painter, (10.5, 7), (5.5, 12))
    elif name == 'presenter':
        painter.drawRoundedRect(QRectF(2.5, 2.5, 11, 8), .6, .6)
        _polyline(painter, (8, 10.5), (8, 13.5))
        _polyline(painter, (5, 13.5), (11, 13.5))
        _polyline(painter, (5.5, 7.5), (7.5, 5.5), (10.5, 7.5))
    elif name in ('security', 'unlock'):
        painter.drawRoundedRect(QRectF(3.5, 7, 9, 6.5), .7, .7)
        if name == 'security':
            _curve(painter, ((5, 7), (4, .5), (12, .5), (11, 7)))
        else:
            _curve(painter, ((5, 7), (4, 1), (11.5, 1), (11.5, 4)))
        _polyline(painter, (8, 9.5), (8, 11))
    elif name == 'export':
        _polyline(painter, (7.5, 2.5), (2.5, 2.5), (2.5, 13.5), (12, 13.5), (12, 10))
        _polyline(painter, (6.5, 9), (13.5, 2.5))
        _polyline(painter, (8.5, 2.5), (13.5, 2.5), (13.5, 7.5))
    elif name == 'optimize':
        _polyline(painter, (2.5, 2.5), (6.5, 6.5))
        _polyline(painter, (6.5, 3), (6.5, 6.5), (3, 6.5))
        _polyline(painter, (13.5, 13.5), (9.5, 9.5))
        _polyline(painter, (9.5, 13), (9.5, 9.5), (13, 9.5))
    elif name == 'search':
        painter.drawEllipse(QRectF(2.5, 2.5, 8, 8))
        _polyline(painter, (9.5, 9.5), (13.5, 13.5))


class _ActionIconEngine(QIconEngine):
    def __init__(self, name, owner=None):
        super().__init__()
        self.name = _canonical(name)
        self._owner = weakref.ref(owner) if owner is not None else None

    def clone(self):
        return _ActionIconEngine(self.name, self._owner() if self._owner else None)

    def key(self):
        return 'EoingPDFActionIcon'

    def iconName(self):
        return self.name

    def isNull(self):
        return False

    def _palette(self):
        owner = self._owner() if self._owner else None
        if owner is not None and isValid(owner):
            if hasattr(owner, 'palette'):
                return owner.palette()
            parent = owner.parent()
            if parent is not None and hasattr(parent, 'palette'):
                return parent.palette()
        return QApplication.palette()

    def paint(self, painter, rect, mode, state):
        if rect.isEmpty():
            return
        group = QPalette.ColorGroup.Disabled if mode == QIcon.Mode.Disabled else QPalette.ColorGroup.Active
        owner = self._owner() if self._owner else None
        menu_active = (mode == QIcon.Mode.Active and owner is not None
                       and isValid(owner) and isinstance(owner, QMenu))
        # Fusion menus request Active for the selected row; a hovered toolbar
        # button also requests Active, so only menu-owned icons use this role.
        role = (QPalette.ColorRole.HighlightedText if mode == QIcon.Mode.Selected or menu_active
                else QPalette.ColorRole.ButtonText)
        color = self._palette().color(group, role)
        side = min(rect.width(), rect.height())
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.translate(rect.x() + (rect.width() - side) / 2,
                              rect.y() + (rect.height() - side) / 2)
            painter.scale(side / 16, side / 16)
            painter.setPen(QPen(color, 1.4, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            _draw_symbol(painter, self.name)
        finally:
            painter.restore()

    def pixmap(self, size, mode, state):
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size, mode, state, scale):
        if size.isEmpty():
            return QPixmap()
        scale = float(scale)
        if not math.isfinite(scale) or scale <= 0:
            scale = 1.0
        raster = QPixmap(max(1, round(size.width() * scale)), max(1, round(size.height() * scale)))
        raster.setDevicePixelRatio(scale)
        raster.fill(Qt.GlobalColor.transparent)
        painter = QPainter(raster)
        try:
            self.paint(painter, QRectF(0, 0, size.width(), size.height()), mode, state)
        finally:
            painter.end()
        return raster


def action_icon(name, owner=None, *, palette_source=None):
    """Return an uncached vector icon that follows the current text palette."""
    source = palette_source if palette_source is not None else owner
    return QIcon(_ActionIconEngine(name, source))


def set_action_icon(button, name, size=16):
    """Apply an icon using this control's palette without retaining the control."""
    name = _canonical(name)
    button.setIcon(action_icon(name, button))
    if hasattr(button, 'setIconSize'):
        button.setIconSize(QSize(int(size), int(size)))
    button.setProperty('actionIcon', name)
    return button


def tool_icon(key, category=None, owner=None, *, palette_source=None):
    """Use the action glyph when known, otherwise its task category glyph."""
    name = _TOOL_ICONS.get(str(key), _CATEGORY_ICONS.get(str(category), 'tools'))
    return action_icon(name, owner, palette_source=palette_source)
