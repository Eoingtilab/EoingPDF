"""Documented DWM window materials; no hooks, timers, or background services.

Qt content surfaces remain opaque. DWM owns the material in the native frame;
PDF, capture, and ink pixels are never made translucent or color-transformed.
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class Policy:
    build: int = 0
    high_contrast: bool = False
    transparency: bool = False
    remote: bool = False
    battery_saver: bool = False
    composition: bool = False

    def material(self, transient=False):
        if (self.build < 22621 or self.high_contrast or not self.transparency
                or self.remote or self.battery_saver or not self.composition):
            return 1  # DWMSBT_NONE
        return 3 if transient else 2  # Desktop Acrylic / Mica


def read_policy():
    if sys.platform != 'win32':
        return Policy()
    import winreg

    class HighContrast(ctypes.Structure):
        _fields_ = [('size', wintypes.UINT), ('flags', wintypes.DWORD), ('scheme', wintypes.LPWSTR)]

    class PowerStatus(ctypes.Structure):
        _fields_ = [('ac', ctypes.c_ubyte), ('flag', ctypes.c_ubyte),
                    ('percent', ctypes.c_ubyte), ('saver', ctypes.c_ubyte),
                    ('remaining', wintypes.DWORD), ('full', wintypes.DWORD)]

    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        contrast = HighContrast(ctypes.sizeof(HighContrast), 0, None)
        # Unknown accessibility state conservatively disables materials.
        high_contrast = (not user32.SystemParametersInfoW(0x42, contrast.size, ctypes.byref(contrast), 0)
                         or bool(contrast.flags & 1))
        transparency = False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                transparency = bool(winreg.QueryValueEx(key, 'EnableTransparency')[0])
        except OSError:
            pass
        power = PowerStatus()
        saver = not kernel32.GetSystemPowerStatus(ctypes.byref(power)) or bool(power.saver)
        composition = wintypes.BOOL()
        result = ctypes.windll.dwmapi.DwmIsCompositionEnabled(ctypes.byref(composition))
        return Policy(sys.getwindowsversion().build, high_contrast, transparency,
                      bool(user32.GetSystemMetrics(0x1000)), saver,
                      result == 0 and bool(composition.value))
    except (AttributeError, OSError):
        return Policy()


def set_attribute(hwnd, attribute, value):
    try:
        function = ctypes.windll.dwmapi.DwmSetWindowAttribute
        function.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        function.restype = ctypes.c_long
        data = wintypes.DWORD(value)
        return function(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data)) == 0
    except (AttributeError, OSError):
        return False


def apply_frame(hwnd, mode, policy, *, transient=False, audience=False):
    """Unsupported Windows builds keep their own native frame without API tricks."""
    if not hwnd or policy.build < 22000:
        return 'unsupported'
    dark = mode == 'dark' and not policy.high_contrast
    set_attribute(hwnd, 20, int(dark))  # DWMWA_USE_IMMERSIVE_DARK_MODE
    if policy.build < 22621:
        return 'solid'
    material = 1 if audience else policy.material(transient)
    if not set_attribute(hwnd, 38, material):  # DWMWA_SYSTEMBACKDROP_TYPE
        set_attribute(hwnd, 38, 1)
        return 'solid'
    return {1: 'solid', 2: 'mica', 3: 'acrylic'}[material]


def install_window_effects(app, theme):
    from PySide6.QtCore import QObject, QEvent, QAbstractNativeEventFilter, QTimer, Qt
    from PySide6.QtWidgets import QWidget, QDialog

    if sys.platform != 'win32' or app.platformName() != 'windows':
        return None
    existing = getattr(app, 'eoing_window_effects', None)
    if existing is not None:
        return existing

    class NativeEvents(QAbstractNativeEventFilter):
        def nativeEventFilter(self, event_type, message):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message in (0x001A, 0x031A, 0x031E, 0x0218, 0x02B1):
                manager.schedule_refresh()
            return False, 0

    class WindowEffects(QObject):
        def __init__(self):
            super().__init__(app)
            self.policy = read_policy()
            self.pending = False

        def apply_window(self, widget):
            if not isinstance(widget, QWidget) or not widget.isWindow():
                return
            # internalWinId never creates handles for hidden/temporary widgets.
            hwnd = int(widget.internalWinId())
            if not hwnd or widget.windowType() in (Qt.ToolTip, Qt.Popup, Qt.SplashScreen):
                return
            mode = 'dark' if widget.property('eoingAudience') else theme.mode
            result = apply_frame(hwnd, mode, self.policy, transient=isinstance(widget, QDialog),
                                 audience=bool(widget.property('eoingAudience')))
            if widget.property('eoingFrameMaterial') != result:
                widget.setProperty('eoingFrameMaterial', result)

        def refresh(self):
            self.pending = False
            self.policy = read_policy()
            for widget in app.topLevelWidgets():
                if widget.isVisible():
                    self.apply_window(widget)

        def schedule_refresh(self):
            if not self.pending:
                self.pending = True
                QTimer.singleShot(0, self, self.refresh)

        def eventFilter(self, watched, event):
            if event.type() in (QEvent.Show, QEvent.WinIdChange):
                self.apply_window(watched)
            elif event.type() == QEvent.ApplicationActivate:
                self.schedule_refresh()
            return False

        def close(self):
            app.removeEventFilter(self)
            app.removeNativeEventFilter(self.native_filter)
            theme.changed.disconnect(self.refresh)

    manager = WindowEffects()
    manager.native_filter = NativeEvents()
    app.installEventFilter(manager)
    app.installNativeEventFilter(manager.native_filter)
    theme.changed.connect(manager.refresh)
    app.aboutToQuit.connect(manager.close)
    app.eoing_window_effects = manager
    manager.refresh()
    return manager
