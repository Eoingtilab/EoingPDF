"""Connect the transient native overlay to the slideshow's existing ink model."""
from .localization import tr
import ctypes as c
from ctypes import wintypes as w

from PySide6.QtCore import QObject, QTimer, Qt, QEvent, QPointF, QCoreApplication, Signal
from PySide6.QtGui import QMouseEvent

from .native_ink import NativeInk


class InkController(QObject):
    failed = Signal(str)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.native = None
        self.active = False
        self.disabled = False
        self.frame = QTimer(self)
        self.frame.setSingleShot(True)
        self.frame.setTimerType(Qt.PreciseTimer)
        self.frame.setInterval(8)
        self.frame.timeout.connect(self.sync)
        self.user = c.WinDLL('user32', use_last_error=True)
        self.user.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
        self.user.ClientToScreen.argtypes = [w.HWND, c.POINTER(w.POINT)]
        canvas.window().installEventFilter(self)
        canvas.destroyed.connect(self.close)

    def request(self):
        if not self.disabled and not self.frame.isActive():
            self.frame.start()

    def sync(self):
        canvas = self.canvas
        if not canvas.isVisible() or canvas.window().isMinimized() or canvas.mask_suspended or canvas.text_editor.isVisible():
            self.hide()
            return
        if not canvas.ink_enabled and not canvas.ink_strokes:
            self.hide()
            return
        page = canvas.page_rect()
        if page.isEmpty():
            self.hide()
            return
        try:
            # GetClientRect/ClientToScreen operate in the Qt process's per-monitor
            # DPI context and avoid multiplying mixed-DPI desktop origins.
            rect, origin = w.RECT(), w.POINT()
            hwnd = int(canvas.winId())
            if not self.user.GetClientRect(hwnd, c.byref(rect)) or not self.user.ClientToScreen(hwnd, c.byref(origin)):
                raise OSError(tr('판서 화면 위치를 확인할 수 없습니다.'))
            sx = (rect.right - rect.left) / max(1, canvas.width())
            sy = (rect.bottom - rect.top) / max(1, canvas.height())
            if self.native is None:
                self.native = NativeInk(int(canvas.window().winId()), self.on_input)
            self.native.resize(origin.x + round(page.left() * sx), origin.y + round(page.top() * sy),
                               max(1, round(page.width() * sx)), max(1, round(page.height() * sy)))
            self.native.mode(canvas.ink_enabled)
            self.native.render(canvas.ink_strokes, canvas.ink_width * sx)
            self.native.show(True)
            if not self.active:
                self.active = True
                canvas.update()
        except Exception as error:
            self.close()
            self.disabled = True
            canvas.update()
            self.failed.emit(str(error))

    def on_input(self, message, x, y):
        if message == 0x0215:
            self.canvas._ink_current = None
            return
        if self.native is None:
            return
        page = self.canvas.page_rect()
        width, height = self.native.size
        position = QPointF(page.left() + x / max(1, width) * page.width(),
                           page.top() + y / max(1, height) * page.height())
        event_type, button, buttons = {
            0x0201: (QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton),
            0x0200: (QEvent.MouseMove, Qt.NoButton, Qt.LeftButton if self.canvas._ink_current else Qt.NoButton),
            0x0202: (QEvent.MouseButtonRelease, Qt.LeftButton, Qt.NoButton),
            0x0204: (QEvent.MouseButtonPress, Qt.RightButton, Qt.RightButton),
            0x0203: (QEvent.MouseButtonDblClick, Qt.LeftButton, Qt.LeftButton),
        }[message]
        QCoreApplication.sendEvent(self.canvas, QMouseEvent(event_type, position, position, button, buttons, Qt.NoModifier))
        self.request()

    def hide(self):
        self.frame.stop()
        if self.native is not None:
            self.native.mode(False)
            self.native.show(False)
        self.active = False

    def close(self, *_):
        self.frame.stop()
        if self.native is not None:
            self.native.close()
            self.native = None
        self.active = False

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.WindowStateChange):
            self.request()
        elif event.type() == QEvent.Hide:
            self.hide()
        return False
