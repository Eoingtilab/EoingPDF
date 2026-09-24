"""Qt adapter consuming the pinned, unmodified NalaApps WPF color resources."""
from .localization import tr
import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree
from weakref import WeakKeyDictionary

_styles = WeakKeyDictionary()


def theme_colors(mode='light'):
    """Dark tones preserve SDK hues; upstream currently provides light only."""
    result = dict(colors())
    if mode == 'light':
        return result
    if mode != 'dark':
        raise ValueError('Unknown theme')
    from PySide6.QtGui import QColor
    # Role-based luminance, not inversion: documents and image pixels are untouched.
    tones = {
        'AppBackground': .075, 'Sidebar': .09, 'Surface': .12,
        'SurfaceSoft': .15, 'SurfaceHover': .20, 'SurfaceSelected': .22,
        'TextStrong': .96, 'Text': .89, 'TextMuted': .70,
        'Border': .28, 'BorderStrong': .40,
        'Primary': .48, 'PrimaryHover': .43, 'PrimaryPressed': .38,
        'Focus': .72, 'Success': .70, 'Danger': .72, 'Warning': .72,
        'AccentViolet': .73, 'AccentCyan': .70,
    }
    for role, lightness in tones.items():
        color = QColor(result[role])
        hue, saturation, _, alpha = color.getHslF()
        if role in {'Surface', 'Sidebar', 'AppBackground', 'SurfaceSoft', 'SurfaceHover'}:
            hue, saturation = QColor(result['Text']).hslHueF(), .18
        elif role == 'SurfaceSelected':
            saturation = .35
        result[role] = QColor.fromHslF(max(0, hue), saturation, lightness, alpha).name()
    return result


def apply_style(widget, style):
    """Retain source styles so changing theme never accumulates color substitutions."""
    from PySide6.QtWidgets import QApplication
    _styles[widget] = str(style)
    app = QApplication.instance()
    controller = getattr(app, 'eoing_theme', None)
    widget.setStyleSheet(adapt_style(str(style), controller.mode if controller else 'light'))


def install_theme(app, settings=None):
    """Window-scoped system theme signals, with no polling or background process."""
    from PySide6.QtCore import QObject, QSettings, Qt, Signal
    from shiboken6 import isValid

    if getattr(app, 'eoing_theme', None) is not None:
        return app.eoing_theme

    class ThemeController(QObject):
        changed = Signal(str)

        def __init__(self):
            super().__init__(app)
            self.settings = settings if settings is not None else QSettings('Eoingtilab', 'EoingPDF')
            preference = str(self.settings.value('appearance/theme', 'system'))
            self.preference = preference if preference in ('system', 'light', 'dark') else 'system'
            self.mode = 'light'
            self.applying = False
            app.styleHints().colorSchemeChanged.connect(self.system_changed)

        def set_preference(self, preference):
            if preference not in ('system', 'light', 'dark'):
                raise ValueError('Unknown theme preference')
            self.preference = preference
            self.settings.setValue('appearance/theme', preference)
            self.apply()

        def system_changed(self, scheme):
            if self.preference == 'system' and not self.applying:
                self.apply(reset_scheme=False)

        def apply(self, reset_scheme=True):
            if self.applying:
                return
            self.applying = True
            try:
                if reset_scheme:
                    scheme = {'system': Qt.ColorScheme.Unknown, 'light': Qt.ColorScheme.Light,
                              'dark': Qt.ColorScheme.Dark}[self.preference]
                    app.styleHints().setColorScheme(scheme)
                self.mode = ('dark' if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else 'light') if self.preference == 'system' else self.preference
                install_palette(app, self.mode, set_scheme=False)
                for widget, style in list(_styles.items()):
                    if isValid(widget):
                        widget.setStyleSheet(adapt_style(style, self.mode))
                self.changed.emit(self.mode)
            finally:
                self.applying = False

    app.eoing_theme = ThemeController()
    app.eoing_theme.apply()
    from .windows_effects import install_window_effects
    install_window_effects(app, app.eoing_theme)
    return app.eoing_theme


@lru_cache(maxsize=1)
def colors():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    folder = root / 'assets/nalapps-sdk'
    source = (folder / 'NalaApps.DesignSystem.xaml').read_bytes()
    provenance = json.loads((folder / 'provenance.json').read_text(encoding='utf-8-sig'))
    if hashlib.sha256(source).hexdigest() != provenance['sha256']:
        raise ValueError(tr('공통 SDK 디자인 리소스가 손상되었습니다. 앱을 다시 설치해 주세요.'))
    result = {}
    for element in ElementTree.fromstring(source):
        key = element.get('{http://schemas.microsoft.com/winfx/2006/xaml}Key', '')
        if element.tag.endswith('}Color') and key.startswith('NalaApps.Color.'):
            value = (element.text or '').strip()
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                raise ValueError(tr('지원하지 않는 SDK 색상 형식입니다.'))
            result[key.removeprefix('NalaApps.Color.')] = value
    required = {'Primary', 'PrimaryHover', 'PrimaryPressed', 'Text', 'TextStrong',
                'TextMuted', 'Border', 'BorderStrong', 'Surface', 'SurfaceSoft',
                'SurfaceSelected', 'SurfaceHover', 'AppBackground', 'Danger', 'Success', 'Focus'}
    if not required.issubset(result):
        raise ValueError(tr('SDK 디자인 토큰이 누락되었습니다.'))
    return result


def adapt_style(style, mode="light"):
    """Map legacy Qt roles to SDK tokens without modifying the upstream theme."""
    roles = {
        'Text': ('#263246', '#26364d', '#193455'),
        'TextStrong': ('#192b49', '#172a47', '#183b8f'),
        'TextMuted': ('#95a0b3', '#778398', '#8994a6', '#657187', '#94a0b3', '#8b9bb1', '#a5adba'),
        'AppBackground': ('#f7f9fc', '#f8faff'),
        'SurfaceSoft': ('#f9fbff', '#f9fbfd', '#f1f4f9', '#eef2f8', '#f6f8fc', '#e8edf5', '#edf2f9', '#eef1f6', '#e8edf7', '#e3eafa', '#ecf6f2'),
        'SurfaceHover': ('#f1f5fb', '#f4f6fb', '#c5d0f3'),
        'SurfaceSelected': ('#edf2ff', '#eff3ff', '#dbe6ff'),
        'Primary': ('#416ae6', '#4b70ed', '#5578df', '#375dcc', '#6385ed', '#5176ec'),
        'PrimaryHover': ('#3e61d8',),
        'Focus': ('#7c9dfa', '#6989ef', '#4f6bff'),
        'Border': ('#e7ecf3', '#e2e7ef', '#e4eaf3', '#e1e7f0', '#dae2f0', '#dbe5f5', '#e7ebf2', '#f0f3f8', '#e2d5d9'),
        'BorderStrong': ('#c6d3e6', '#b9cbed'),
        'Success': ('#458475',),
        'Danger': ('#b33445',),
    }
    tokens = theme_colors(mode)
    mapping = {old: tokens[role] for role, legacy in roles.items() for old in legacy}
    # Also accept already-adapted light styles imported before QApplication.
    for role, value in colors().items():
        if role not in {'Surface', 'OnPrimary', 'OnDanger'}:
            mapping[value.lower()] = tokens[role]
    style = re.sub(r'(?i)(background(?:-color)?\s*:\s*)(?:white|#fff(?:fff)?)(?=[; }])',
                   lambda match: match[1] + tokens['Surface'], style)
    style = re.sub(r'#[0-9a-fA-F]{6}\b', lambda match: mapping.get(match[0].lower(), match[0]), style)
    if mode == 'dark':
        # Primary-filled buttons keep white labels; blue text needs a lighter
        # tone on dark navigation, links and selected list rows.
        style = re.sub(r'(?i)((?:^|[;{\s])(?:selection-)?color\s*:\s*)' + re.escape(tokens['Primary']) + r'\b',
                       lambda match: match[1] + tokens['Focus'], style)
    return style


def install_palette(app, mode="light", *, set_scheme=True):
    """Apply semantic colors to unstyled controls as well as styled windows."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    tokens = theme_colors(mode)
    if set_scheme:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if mode == 'dark' else Qt.ColorScheme.Light)
    palette = QPalette()
    roles = {
        'Window': 'AppBackground', 'WindowText': 'Text', 'Base': 'Surface',
        'AlternateBase': 'SurfaceSoft', 'Text': 'Text', 'Button': 'Surface',
        'ButtonText': 'Text', 'ToolTipBase': 'Surface', 'ToolTipText': 'Text',
        'Highlight': 'Primary', 'HighlightedText': 'OnPrimary',
        'Link': 'Primary', 'LinkVisited': 'AccentViolet', 'PlaceholderText': 'TextMuted',
        'Light': 'Surface', 'Midlight': 'SurfaceSoft', 'Mid': 'Border',
        'Dark': 'BorderStrong', 'Shadow': 'TextStrong', 'BrightText': 'OnPrimary',
    }
    for role, token in roles.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(tokens[token]))
    for role in ('WindowText', 'Text', 'ButtonText'):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(tokens['TextMuted']))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(tokens['SurfaceSoft']))
    app.setPalette(palette)
