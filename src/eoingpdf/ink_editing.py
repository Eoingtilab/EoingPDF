"""Local annotation editing: per-surface history, shapes, erasing and pictures."""
import math
import hashlib
from PySide6.QtCore import Qt, QPointF, QRectF, QBuffer, QIODevice
from PySide6.QtGui import QColor, QPen
from .ink_stroke import InkStroke
from .localization import tr


def clone(stroke, points=None):
    result = InkStroke([QPointF(point) for point in (stroke if points is None else points)], stroke.kind)
    result.__dict__.update(stroke.__dict__)
    return result


def signature(strokes):
    return [(tuple((p.x(), p.y()) for p in s), s.kind, s.color, s.width, s.opacity,
             getattr(s, 'image_png', b'')) for s in strokes if s.kind != 'ghost']


def bounds(strokes):
    points = [p for s in strokes for p in s]
    if not points:
        return QRectF()
    xs, ys = [p.x() for p in points], [p.y() for p in points]
    return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def shape_points(first, last, kind):
    x0, x1 = sorted((first.x(), last.x()))
    y0, y1 = sorted((first.y(), last.y()))
    if kind == 'rectangle':
        return [QPointF(x0, y0), QPointF(x1, y0), QPointF(x1, y1), QPointF(x0, y1), QPointF(x0, y0)]
    if kind == 'ellipse':
        return [QPointF((x0 + x1) / 2 + (x1 - x0) / 2 * math.cos(i * math.tau / 64),
                       (y0 + y1) / 2 + (y1 - y0) / 2 * math.sin(i * math.tau / 64)) for i in range(65)]
    return [first, last]


def erase_paths(strokes, center, radius, size):
    """Cut intersecting line segments at the eraser circle, preserving other ink."""
    width, height = size
    output = []
    for stroke in strokes:
        if stroke.kind == 'image':
            output.append(stroke)
            continue
        area = bounds([stroke])
        pixel_box = QRectF(area.x() * width, area.y() * height, area.width() * width, area.height() * height)
        if not pixel_box.adjusted(-radius, -radius, radius, radius).contains(center):
            output.append(stroke)
            continue
        if stroke.fill:
            if not pixel_box.intersects(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)):
                output.append(stroke)
            continue
        fragments, current = [], []
        for first, last in zip(stroke, stroke[1:]):
            a = QPointF(first.x() * width, first.y() * height)
            b = QPointF(last.x() * width, last.y() * height)
            delta, offset = b - a, a - center
            aa = delta.x() ** 2 + delta.y() ** 2
            bb = 2 * (offset.x() * delta.x() + offset.y() * delta.y())
            cc = offset.x() ** 2 + offset.y() ** 2 - radius ** 2
            disc = bb ** 2 - 4 * aa * cc
            cut = None
            if aa > 1e-9 and disc >= 0:
                lo, hi = max(0, (-bb - math.sqrt(disc)) / (2 * aa)), min(1, (-bb + math.sqrt(disc)) / (2 * aa))
                if lo < hi:
                    cut = lo, hi
            if cut is None:
                if not current:
                    current.append(first)
                current.append(last)
                continue
            lo, hi = cut
            if lo > 0:
                if not current:
                    current.append(first)
                current.append(first + (last - first) * lo)
            if len(current) > 1:
                fragments.append(current)
            current = [first + (last - first) * hi, last] if hi < 1 else []
        if len(current) > 1:
            fragments.append(current)
        output.extend(clone(stroke, points) for points in fragments)
    return output


class InkEditing:
    def init_editing(self):
        self.ink_color = (1, .82, 0)
        self.custom_ink_color = False
        self.stroke_width = 2.5
        self.text_size = 18
        self.shape_fill = False
        self.selected_ink = None
        self._edit_drag = None
        self._edit_before = None
        self._histories = {}
        self._text_group = 0
        self._picture_cache = {}
        self._picture_bytes = 0

    def history(self):
        return self._histories.setdefault(id(self.ink_strokes), [self.ink_strokes, [], []])

    def start_edit(self):
        self._edit_before = [clone(s) for s in self.ink_strokes if s.kind != 'ghost']

    def finish_edit(self):
        if self._edit_before is not None and signature(self._edit_before) != signature(self.ink_strokes):
            history = self.history()
            history[1].append(self._edit_before)
            history[1][:] = history[1][-32:]
            history[2].clear()
            self.trim_history()
        self._edit_before = None

    def trim_history(self):
        stacks = [stack for history in self._histories.values() for stack in history[1:]]
        total = sum(sum(len(stroke) for stroke in snapshot) for stack in stacks for snapshot in stack)
        for stack in stacks:
            while total > 300000 and stack:
                total -= sum(len(stroke) for stroke in stack.pop(0))

    def reset_history(self):
        self._histories.clear()
        self._picture_cache.clear()
        self._picture_bytes = 0

    def undo_ink(self):
        self._restore_history(1, 2)

    def redo_ink(self):
        self._restore_history(2, 1)

    def _restore_history(self, source, target):
        if not self.commit_text():
            return
        history = self.history()
        if history[source]:
            history[target].append([clone(s) for s in self.ink_strokes if s.kind != 'ghost'])
            self.ink_strokes[:] = history[source].pop()
            self.trim_history()
            self.selected_ink = None
            self._ink_current = None
            self._edit_drag = None
            self.update()

    def selection(self):
        selected = self.selected_ink
        if selected is None or selected not in self.ink_strokes:
            return []
        group = getattr(selected, 'group', None)
        return [s for s in self.ink_strokes if group and getattr(s, 'group', None) == group] if group else [selected]

    def delete_selected(self):
        selected = {id(s) for s in self.selection()}
        if selected:
            self.start_edit()
            self.ink_strokes[:] = [s for s in self.ink_strokes if id(s) not in selected]
            self.selected_ink = None
            self.finish_edit()
            self.update()

    def styled_stroke(self, points, kind):
        stroke = InkStroke(points, kind)
        stroke.width, stroke.color = self.stroke_width, self.ink_color
        return stroke

    def add_picture(self, image):
        if image.isNull() or image.width() * image.height() > 12_000_000:
            raise ValueError(tr('이미지는 1200만 픽셀 이하로 선택해 주세요.'))
        if sum(s.kind == 'image' for s in self.ink_strokes) >= 16:
            raise ValueError(tr('한 화면에 이미지는 최대 16개까지 넣을 수 있습니다.'))
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer, 'PNG'):
            raise ValueError(tr('이미지를 읽을 수 없습니다.'))
        width, height = self.page_size
        aspect = image.width() / image.height()
        w = min(width * .45, height * .45 * aspect)
        h = w / aspect
        x, y = (1 - w / width) / 2, (1 - h / height) / 2
        stroke = InkStroke([QPointF(x, y), QPointF(x + w / width, y + h / height)], 'image')
        stream = bytes(buffer.data())
        identity = hashlib.sha256(stream).digest()
        if identity not in self._picture_cache:
            preview = image.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            size = len(stream) + preview.sizeInBytes()
            if self._picture_bytes + size > 96 * 1024 * 1024:
                raise ValueError(tr('이미지 메모리 한도에 도달했습니다. 판서를 저장한 뒤 계속해 주세요.'))
            self._picture_cache[identity] = (stream, preview)
            self._picture_bytes += size
        stroke.image_png, stroke.image_preview = self._picture_cache[identity]
        stroke.opacity = 1
        self.start_edit()
        self.ink_strokes.append(stroke)
        self.finish_edit()
        self.selected_ink = stroke
        self.set_tool('select')
        self.update()

    def ink_pixel_bounds(self, strokes):
        area, page = bounds(strokes), self.page_rect()
        return QRectF(page.x() + area.x() * page.width(), page.y() + area.y() * page.height(),
                      area.width() * page.width(), area.height() * page.height())

    def editing_press(self, position):
        tool = self.ink_tool
        if tool not in ('erase', 'select', 'line', 'rectangle', 'ellipse', 'arrow'):
            return False
        if not self.page_rect().contains(position):
            return True
        point = self._normalized(position)
        self.start_edit()
        if tool == 'erase':
            self._edit_drag = ('erase',)
            self.erase_at(position)
        elif tool == 'select':
            selected = self.selection()
            box = self.ink_pixel_bounds(selected) if selected else QRectF()
            resize = selected and QRectF(box.right() - 8, box.bottom() - 8, 16, 16).contains(position)
            if not resize:
                self.selected_ink = next((s for s in reversed(self.ink_strokes)
                    if self.ink_pixel_bounds([t for t in self.ink_strokes if getattr(t, 'group', None) == s.group]
                                            if getattr(s, 'group', None) else [s]).adjusted(-5, -5, 5, 5).contains(position)), None)
                selected = self.selection()
            self._edit_drag = ('resize' if resize else 'move', point, bounds(selected), [(s, list(s)) for s in selected]) if selected else None
        else:
            stroke = self.styled_stroke([point, point], 'shape')
            stroke.shape = tool
            stroke.fill = self.shape_fill and tool in ('rectangle', 'ellipse')
            self.ink_strokes.append(stroke)
            self._edit_drag = ('shape', point, stroke, tool)
        self.setCursor(Qt.CrossCursor)
        self.update()
        return True

    def erase_at(self, position):
        page = self.page_rect()
        center = position - page.topLeft()
        self.ink_strokes[:] = erase_paths(self.ink_strokes, center, max(6, self.ink_width * self.stroke_width / 2.5 * 2),
                                          (page.width(), page.height()))

    def editing_move(self, position):
        if not self._edit_drag:
            return False
        mode, *data = self._edit_drag
        point = self._normalized(position)
        if mode == 'erase':
            self.erase_at(position)
        elif mode == 'shape':
            first, stroke, kind = data
            stroke[:] = shape_points(first, point, kind)
            if kind == 'arrow':
                width, height = self.page_size
                dx, dy = (point.x() - first.x()) * width, (point.y() - first.y()) * height
                angle, length = math.atan2(dy, dx), min(16, math.hypot(dx, dy) / 3)
                a, b = [QPointF(point.x() - length * math.cos(angle + sign * .5) / width,
                                point.y() - length * math.sin(angle + sign * .5) / height) for sign in (-1, 1)]
                stroke[:] = [first, point, QPointF(max(0, min(1, a.x())), max(0, min(1, a.y()))), point,
                             QPointF(max(0, min(1, b.x())), max(0, min(1, b.y())))]
        else:
            origin, area, objects = data
            if mode == 'move':
                delta = point - origin
                dx = max(-area.left(), min(delta.x(), 1 - area.right()))
                dy = max(-area.top(), min(delta.y(), 1 - area.bottom()))
                for stroke, original in objects:
                    stroke[:] = [p + QPointF(dx, dy) for p in original]
            elif area.width() > 1e-6 and area.height() > 1e-6:
                w = max(72 / 25.4 / self.page_size[0], .005, point.x() - area.left())
                h = max(.005, point.y() - area.top())
                if objects[0][0].kind == 'image':
                    h = w * area.height() / area.width()
                scale = min(1, (1 - area.left()) / w, (1 - area.top()) / h)
                w, h = w * scale, h * scale
                for stroke, original in objects:
                    stroke[:] = [QPointF(area.x() + (p.x() - area.x()) * w / area.width(),
                                        area.y() + (p.y() - area.y()) * h / area.height()) for p in original]
        self.update()
        return True

    def editing_release(self, position):
        if self._edit_drag:
            self.editing_move(position)
            self._edit_drag = None
            self.finish_edit()
            return True
        return self.ink_tool in ('erase', 'select')

    def paint_pictures(self, painter):
        for stroke in self.ink_strokes:
            if stroke.kind == 'image':
                painter.drawImage(self.ink_pixel_bounds([stroke]), stroke.image_preview)

    def paint_selection(self, painter):
        selected = self.selection()
        if selected:
            box = self.ink_pixel_bounds(selected)
            painter.setPen(QPen(QColor('#497dff'), 2))
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawRect(box)
            painter.setBrush(QColor('white'))
            painter.drawRect(QRectF(box.right() - 6, box.bottom() - 6, 12, 12))
