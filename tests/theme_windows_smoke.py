"""Real Windows Qt/DWM integration, without modifying OS appearance settings."""
import ctypes
from ctypes import wintypes
from dataclasses import asdict, replace
import json
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.app import Window, STYLE
from eoingpdf.sdk_theme import apply_style, install_theme
from eoingpdf.settings_ui import SettingsDialog
from eoingpdf.viewer import SlideShow


def attribute(hwnd, number):
    value = wintypes.DWORD()
    function = ctypes.windll.dwmapi.DwmGetWindowAttribute
    function.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    function.restype = ctypes.c_long
    result = function(hwnd, number, ctypes.byref(value), ctypes.sizeof(value))
    assert result == 0, (number, result)
    return value.value


def main():
    app = QApplication([])
    assert sys.platform == 'win32' and app.platformName() == 'windows', 'Real Windows Qt backend required'
    folder = ROOT / 'temp/theme-windows'
    folder.mkdir(parents=True, exist_ok=True)
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    theme = install_theme(app, QSettings(str(folder / 'smoke.ini'), QSettings.IniFormat))
    apply_style(app, STYLE)
    effects = app.eoing_window_effects
    original_policy = effects.policy
    report = {'policy': asdict(original_policy), 'screens': [], 'windows': []}
    for screen in app.screens():
        report['screens'].append({'width': screen.size().width(), 'height': screen.size().height(),
                                  'dpr': screen.devicePixelRatio(), 'dpi': screen.logicalDotsPerInch()})
    path = folder / 'slide.pdf'
    with pdf.open() as document:
        page = document.new_page(width=960, height=540)
        page.insert_text((60, 70), 'Original PDF colors', fontsize=24)
        page.draw_rect((60, 100, 260, 240), fill=(0.9, 0.15, 0.05))
        document.save(path)
    window, settings, show = Window(), SettingsDialog(), SlideShow(path)
    window.resize(1100, 780)
    show.resize(1100, 700)
    try:
        for mode in ('light', 'dark', 'light'):
            theme.set_preference(mode)
            for name, widget, transient, audience in [('main', window, False, False),
                                                        ('settings', settings, True, False),
                                                        ('audience', show, True, True)]:
                widget.show()
                widget.raise_()
                widget.activateWindow()
                QTest.qWait(180)
                hwnd = int(widget.winId())
                row = {'window': name, 'theme': mode, 'material': widget.property('eoingFrameMaterial')}
                if original_policy.build >= 22000:
                    row['dark'] = attribute(hwnd, 20)
                    assert row['dark'] == int((audience or mode == 'dark') and not original_policy.high_contrast)
                if original_policy.build >= 22621:
                    row['backdrop'] = attribute(hwnd, 38)
                    assert row['backdrop'] == (1 if audience else original_policy.material(transient))
                report['windows'].append(row)
                # QWidget capture works even on a noninteractive test desktop.
                # It verifies client pixels; native-frame evidence is DWM readback.
                widget.grab().save(str(folder / f'{name}-{mode}.png'))
                widget.hide()
        if original_policy.build >= 22621:
            settings.show()
            QTest.qWait(100)
            for override in ({'high_contrast': True}, {'transparency': False}, {'remote': True}):
                effects.policy = replace(original_policy, **override)
                effects.apply_window(settings)
                assert attribute(int(settings.winId()), 38) == 1
            report['injected_policy_fallbacks'] = ['high_contrast', 'transparency_disabled', 'remote']
            effects.refresh()
        report['capture_scope'] = 'Qt client pixels; native frame verified by DWM attribute readback'
        (folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        print('PASS: Windows DWM attributes, theme roundtrip, client screenshots; fallback policies injected')
    finally:
        for widget in (show, settings, window):
            widget.close()
        effects.close()


if __name__ == '__main__':
    main()
