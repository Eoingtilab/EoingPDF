import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import sys

import pytest
from PySide6.QtCore import QPointF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.native_ink import NativeInk


@pytest.fixture(autouse=True, params=['dc', 'gpu'])
def selected_backend(request, monkeypatch):
    constructor = NativeInk

    def create(*args, **kwargs):
        overlay = constructor(*args, **kwargs, backend=request.param)
        assert overlay.backend == request.param
        return overlay

    monkeypatch.setattr(sys.modules[__name__], 'NativeInk', create)
    return request.param


@pytest.mark.parametrize('capture', [False, True])
@pytest.mark.parametrize('width,height', [(512, 256), (1536, 768)])
def test_repeated_frame_and_edit_sequence_matches_fresh_render(capture, width, height):
    frames = [
        [[QPointF(.1, .1), QPointF(.2, .2)]],
        [[QPointF(.1, .1), QPointF(.2, .2), QPointF(.23, .22)]],
        [[QPointF(.1, .1), QPointF(.2, .2), QPointF(.23, .22), QPointF(.8, .7)]],
        [[QPointF(.1, .1), QPointF(.2, .2), QPointF(.23, .22), QPointF(.8, .7)],
         [QPointF(.15, .8), QPointF(.5, .5)]],
        [[QPointF(.1, .1), QPointF(.2, .2), QPointF(.23, .22), QPointF(.8, .7)],
         [QPointF(.15, .8), QPointF(.5, .5), QPointF(1, 0)]],
        [[QPointF(.1, .1), QPointF(.2, .2)]],
        [[QPointF(.1, .8), QPointF(.6, .1)]],
        [],
    ]
    with NativeInk() as incremental:
        incremental.resize(0, 0, width, height)
        incremental.mode(capture)
        for frame_index, strokes in enumerate(frames):
            incremental.render(strokes, 5.5)
            with NativeInk() as full:
                full.resize(0, 0, width, height)
                full.mode(capture)
                full.render(strokes, 5.5)
                actual, expected = incremental.pixels(), full.pixels()
                assert actual == expected, (frame_index, width, height)
            previous = incremental.pixels()
            incremental.render(strokes, 5.5)
            assert incremental.pixels() == previous


def test_frame_cache_invalidates_on_style_mode_size_and_stroke_grouping():
    a, b, d, e = QPointF(.1, .1), QPointF(.8, .8), QPointF(.1, .8), QPointF(.8, .1)
    states = [
        (400, 300, False, 4, [[a, b, d, e]]),
        (400, 300, False, 4, [[a, b], [d, e]]),
        (400, 300, False, 10, [[a, b], [d, e]]),
        (400, 300, True, 10, [[a, b], [d, e]]),
        (600, 450, True, 10, [[a, b], [d, e]]),
        (600, 450, False, 10, [[a, b], [d, e]]),
    ]
    with NativeInk() as cached:
        for width, height, capture, pen, strokes in states:
            cached.resize(0, 0, width, height)
            cached.mode(capture)
            cached.render(strokes, pen)
            with NativeInk() as fresh:
                fresh.resize(0, 0, width, height)
                fresh.mode(capture)
                fresh.render(strokes, pen)
                assert cached.pixels() == fresh.pixels()


def test_native_direct2d_alpha_resize_and_validation():
    with NativeInk() as overlay:
        overlay.resize(-100, -100, 200, 100)
        overlay.render([[QPointF(.1, .5), QPointF(.9, .5)]], 4)
        pixels = overlay.pixels()
        center = (50 * 200 + 100) * 4
        assert pixels[3] == 0
        assert pixels[center + 3] >= 225
        assert pixels[center + 2] > pixels[center + 1] > pixels[center]
        overlay.resize(0, 0, 400, 200)
        overlay.render([], 4)
        assert not any(overlay.pixels())
        with pytest.raises(OSError):
            overlay.resize(0, 0, 100000, 100000)
        with pytest.raises(OSError):
            overlay.render([[QPointF(float('nan'), .5), QPointF(.8, .8)]], 4)
        with pytest.raises(OSError):
            overlay.render([[QPointF(.1, .1), QPointF(.8, .8)]], -1)


def test_mixed_stroke_styles_and_fade_invalidate_frame_cache():
    from eoingpdf.ink_stroke import InkStroke
    from time import monotonic
    pen = InkStroke([QPointF(.1, .1), QPointF(.9, .1)])
    pen.color = (1, 0, 0)
    ghost = InkStroke([QPointF(.1, .5), QPointF(.9, .5)], 'ghost')
    ghost.color = (0, 0, 1)
    highlight = InkStroke([QPointF(.1, .7), QPointF(.9, .7), QPointF(.9, .9), QPointF(.1, .9)], 'highlight')
    highlight.color = (0, 1, 0)
    with NativeInk() as overlay:
        overlay.resize(0, 0, 200, 100)
        overlay.render([pen, ghost, highlight], 4)
        pixels = overlay.pixels()
        assert pixels[(10 * 200 + 100) * 4 + 2] > 200
        assert pixels[(50 * 200 + 100) * 4] > 200
        assert 70 <= pixels[(80 * 200 + 100) * 4 + 1] <= 80
        ghost.created = monotonic() - 3.3
        overlay.render([pen, ghost, highlight], 4)
        faded = overlay.pixels()[(50 * 200 + 100) * 4 + 3]
        assert 80 < faded < 130
        ghost.created = monotonic() - 4
        overlay.render([pen, ghost, highlight], 4)
        assert overlay.pixels()[(50 * 200 + 100) * 4 + 3] == 0


def test_native_click_through_capture_and_owner_thread_lifecycle():
    user = c.WinDLL('user32', use_last_error=True)
    user.GetWindowLongPtrW.argtypes = [w.HWND, c.c_int]
    user.GetWindowLongPtrW.restype = c.c_ssize_t
    user.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user.SendMessageW.restype = w.LPARAM
    user.IsWindow.argtypes = [w.HWND]
    events = []
    overlay = NativeInk(on_input=lambda *args: events.append(args))
    hwnd = overlay.hwnd
    try:
        overlay.resize(0, 0, 200, 100)
        assert user.GetWindowLongPtrW(hwnd, -20) & 0x20
        assert user.SendMessageW(hwnd, 0x0084, 0, 0) == -1  # HTTRANSPARENT
        user.SendMessageW(hwnd, 0x0201, 1, (25 << 16) | 30)
        assert not events
        overlay.mode(True)
        assert not user.GetWindowLongPtrW(hwnd, -20) & 0x20
        assert user.SendMessageW(hwnd, 0x0084, 0, 0) == 1  # HTCLIENT
        overlay.render([], 4)
        assert overlay.pixels()[3] == 1
        user.SendMessageW(hwnd, 0x0201, 1, (25 << 16) | 30)
        user.SendMessageW(hwnd, 0x0202, 0, (40 << 16) | 60)
        assert [event for event in events if event[0] != 0x0215] == [(0x0201, 30, 25), (0x0202, 60, 40)]
        overlay.mode(False)
        assert user.GetWindowLongPtrW(hwnd, -20) & 0x20
    finally:
        overlay.close()
        overlay.close()
    assert not user.IsWindow(hwnd)


def test_native_input_reaches_slideshow_without_advancing(tmp_path):
    from PySide6.QtWidgets import QApplication
    from eoingpdf.viewer import SlideShow
    from eoingpdf.ink_controller import InkController
    import pymupdf as pdf
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'input.pdf'
    with pdf.open() as document:
        document.new_page(width=400, height=300)
        document.new_page()
        document.save(source)
    slides = SlideShow(source)
    slides.resize(800, 700)
    slides.show()
    app.processEvents()
    slides.canvas.toggle_ink()
    controller = InkController(slides.canvas)
    controller.native = NativeInk(on_input=controller.on_input)
    controller.native.resize(0, 0, 800, 600)
    controller.native.mode(True)
    user = c.WinDLL('user32')
    user.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user.SendMessageW.restype = w.LPARAM
    try:
        user.SendMessageW(controller.native.hwnd, 0x0201, 1, (150 << 16) | 160)
        user.SendMessageW(controller.native.hwnd, 0x0200, 1, (300 << 16) | 400)
        user.SendMessageW(controller.native.hwnd, 0x0202, 0, (450 << 16) | 640)
        assert slides.index == 0
        stroke = slides.canvas.ink_strokes[0]
        assert stroke[0] == QPointF(.2, .25)
        assert stroke[-1] == QPointF(.8, .75)
        assert slides.canvas._ink_current is None
    finally:
        controller.close()
        slides.canvas.clear_ink()
        slides.close()
        app.processEvents()
