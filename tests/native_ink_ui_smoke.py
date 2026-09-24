"""Real Windows Qt HWND integration; messages are synthetic, not physical input."""
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import sys
import tempfile
from time import monotonic

os.environ['QT_QPA_PLATFORM'] = 'windows'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtWidgets import QApplication
import pymupdf as pdf
from eoingpdf.viewer import SlideShow


def wait_until(predicate):
    deadline = monotonic() + 5
    while not predicate():
        if monotonic() > deadline:
            raise AssertionError('Windows overlay state did not settle within 5 seconds')
        QTest.qWait(20)


def main():
    app = QApplication([])
    user = c.WinDLL('user32')
    user.IsWindowVisible.argtypes = [w.HWND]
    user.IsWindow.argtypes = [w.HWND]
    user.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
    user.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user.SendMessageW.restype = w.LPARAM
    with tempfile.TemporaryDirectory(prefix='eoing-native-ui-') as folder:
        source = Path(folder) / 'slides.pdf'
        with pdf.open() as document:
            document.new_page(width=400, height=300)
            document.new_page(width=400, height=300)
            document.save(source)
        slides = SlideShow(source)
        slides.resize(960, 700)
        slides.move(120, 120)
        slides.show()
        controller = slides.canvas.native_ink
        assert controller is not None
        try:
            QTest.keyClick(slides, Qt.Key_P)
            wait_until(lambda: controller.active)
            assert controller.native.backend == 'gpu'
            hwnd = controller.native.hwnd
            assert user.IsWindowVisible(hwnd)
            before = w.RECT()
            assert user.GetWindowRect(hwnd, c.byref(before))
            width, height = controller.native.size
            for message, x, y in [(0x0201, width // 4, height // 4),
                                  (0x0200, width // 2, height // 2),
                                  (0x0202, width * 3 // 4, height * 3 // 4)]:
                user.SendMessageW(hwnd, message, 0, (y << 16) | x)
            center_alpha = ((height // 2) * width + width // 2) * 4 + 3
            wait_until(lambda: controller.native.pixels()[center_alpha] > 200)
            assert slides.index == 0 and len(slides.canvas.ink_strokes) == 1
            slides.move(slides.x() + 40, slides.y() + 30)
            after = w.RECT()
            wait_until(lambda: user.GetWindowRect(hwnd, c.byref(after)) and
                       after.left > before.left and after.top > before.top)
            assert after.left > before.left and after.top > before.top
            slide_strokes = slides.canvas.ink_strokes
            QTest.keyClick(slides, Qt.Key_B)
            wait_until(lambda: controller.active and user.IsWindowVisible(hwnd))
            assert not slides.canvas.ink_strokes
            wait_until(lambda: max(controller.native.pixels()[3::4]) <= 1)
            board_width, board_height = controller.native.size
            for message, x, y in [(0x0201, board_width // 4, board_height // 4),
                                  (0x0200, board_width // 2, board_height // 2),
                                  (0x0202, board_width * 3 // 4, board_height * 3 // 4)]:
                user.SendMessageW(hwnd, message, 0, (y << 16) | x)
            board_alpha = ((board_height // 2) * board_width + board_width // 2) * 4 + 3
            wait_until(lambda: controller.native.pixels()[board_alpha] > 200)
            assert len(slides.canvas.ink_strokes) == 1
            assert slides.canvas.ink_strokes is not slide_strokes
            QTest.keyClick(slides, Qt.Key_B)
            wait_until(lambda: controller.active and controller.native.size == (width, height))
            assert slides.canvas.ink_strokes is slide_strokes
            QTest.keyClick(slides, Qt.Key_P)
            wait_until(lambda: user.SendMessageW(hwnd, 0x0084, 0, 0) == -1)
            QTest.keyClick(slides, Qt.Key_T)
            wait_until(lambda: user.SendMessageW(hwnd, 0x0084, 0, 0) == 1)
            user.SendMessageW(hwnd, 0x0201, 1, (height // 4 << 16) | (width // 4))
            wait_until(lambda: slides.canvas.text_editor.isVisible() and not user.IsWindowVisible(hwnd))
            ime = QInputMethodEvent()
            ime.setCommitString('어잉PDF')
            app.sendEvent(slides.canvas.text_editor, ime)
            QTest.keyClick(slides.canvas.text_editor, Qt.Key_Return)
            wait_until(lambda: controller.active and user.IsWindowVisible(hwnd))
            assert any(getattr(stroke, 'text', '') == '어잉PDF' for stroke in slides.canvas.ink_strokes)
            assert not slides.canvas.text_editor.isVisible()
            print('PASS: Windows Qt GPU overlay, native input, movement, separate board ink and idle hit testing')
            print('PASS: native T input opens editor, accepts Korean IME text and resumes GPU rendering')
        finally:
            slides.boards.clear()
            slides.ink_by_slide.clear()
            slides.canvas.clear_ink()
            slides.close()
            app.processEvents()
        assert controller.native is None and not controller.frame.isActive()
        assert not user.IsWindow(hwnd)
        print('PASS: overlay HWND and frame timer released on slideshow close')


if __name__ == '__main__':
    main()

