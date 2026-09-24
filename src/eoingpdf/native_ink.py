"""Thin UI-thread-only interface to the Direct2D layered-window renderer."""
from .localization import tr
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
from functools import lru_cache
import sys


class Point(c.Structure):
    _fields_ = [('x', c.c_float), ('y', c.c_float)]


class StrokeStyle(c.Structure):
    _fields_ = [(name, c.c_float) for name in ('red', 'green', 'blue', 'alpha', 'width')] + [('fill', w.UINT)]


InputCallback = c.WINFUNCTYPE(None, w.UINT, c.c_int, c.c_int)


@lru_cache(maxsize=1)
def load_library():
    # Retain the library for the process lifetime: its registered window class
    # owns a WndProc address inside the DLL even between overlay sessions.
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    path = root / 'assets/EoingPDF.Ink.dll'
    library = c.WinDLL(str(path))
    signatures = {
        'InkCreate': (c.c_void_p, [w.HWND, InputCallback]),
        'InkCreateWithBackend': (c.c_void_p, [w.HWND, InputCallback, c.c_int]),
        'InkBackend': (c.c_int, [c.c_void_p]),
        'InkWait': (c.c_long, [c.c_void_p]),
        'InkDestroy': (None, [c.c_void_p]),
        'InkResize': (c.c_long, [c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_int]),
        'InkRender': (c.c_long, [c.c_void_p, c.POINTER(Point), w.UINT, c.POINTER(w.UINT), w.UINT, c.c_float]),
        'InkRenderStyled': (c.c_long, [c.c_void_p, c.POINTER(Point), w.UINT, c.POINTER(w.UINT), w.UINT, c.c_float, c.POINTER(StrokeStyle)]),
        'InkMode': (None, [c.c_void_p, w.BOOL]),
        'InkShow': (None, [c.c_void_p, w.BOOL]),
        'InkWindow': (w.HWND, [c.c_void_p]),
        'InkCopyPixels': (c.c_long, [c.c_void_p, c.c_void_p, c.c_size_t]),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
    return library


def check(result):
    if result < 0:
        raise OSError(tr('Direct2D 판서 오류: 0x{v0:08X}', v0=result & 0xffffffff))


class NativeInk:
    def __init__(self, owner=0, on_input=lambda message, x, y: None, backend='auto'):
        self.library = load_library()
        self.callback = InputCallback(on_input)
        choice = {'auto': 0, 'dc': 1, 'gpu': 2}[backend]
        self.handle = self.library.InkCreateWithBackend(owner, self.callback, choice)
        self.size = (0, 0)
        if not self.handle:
            raise OSError(tr('Direct2D 판서 창을 만들 수 없습니다.'))

    @property
    def backend(self):
        return 'gpu' if self.library.InkBackend(self.handle) == 2 else 'dc'

    def wait(self):
        check(self.library.InkWait(self.handle))

    @property
    def hwnd(self):
        return self.library.InkWindow(self.handle)

    def resize(self, x, y, width, height):
        check(self.library.InkResize(self.handle, x, y, width, height))
        self.size = width, height

    def mode(self, capture):
        self.library.InkMode(self.handle, capture)

    def show(self, visible):
        self.library.InkShow(self.handle, visible)

    def render(self, strokes, width):
        count = sum(len(stroke) for stroke in strokes)
        if count > 250000 or len(strokes) > 10000:
            raise ValueError(tr('한 페이지 판서 한도에 도달했습니다. 저장 후 계속해 주세요.'))
        points = (Point * count)()
        ends = (w.UINT * len(strokes))()
        styles = (StrokeStyle * len(strokes))()
        offset = 0
        for index, stroke in enumerate(strokes):
            for point in stroke:
                points[offset] = Point(point.x(), point.y())
                offset += 1
            ends[index] = offset
            color = getattr(stroke, 'color', (1, .82, 0))
            opacity = stroke.alpha() if hasattr(stroke, 'alpha') else .9
            styles[index] = StrokeStyle(*color, opacity, width * getattr(stroke, 'width', 2.5) / 2.5,
                                        int(getattr(stroke, 'fill', False)))
        check(self.library.InkRenderStyled(self.handle, points, count, ends, len(strokes), width, styles))

    def pixels(self):
        buffer = (c.c_ubyte * (self.size[0] * self.size[1] * 4))()
        check(self.library.InkCopyPixels(self.handle, buffer, len(buffer)))
        return bytes(buffer)

    def close(self):
        if self.handle:
            self.library.InkDestroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
