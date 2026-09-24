import sys
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.sdk_theme import colors, install_palette


def test_sdk_palette_replaces_dark_popup_colors_and_keeps_disabled_text_readable():
    app = QApplication.instance()
    previous = app.palette()
    scheme = app.styleHints().colorScheme()
    dark = QPalette()
    dark.setColor(QPalette.Base, QColor('#111111'))
    dark.setColor(QPalette.Text, QColor('#ffffff'))
    app.setPalette(dark)
    widgets = []
    try:
        install_palette(app)
        combo, entry = QComboBox(), QLineEdit()
        widgets.extend([combo, entry])
        combo.addItems(['너비 맞춤', '100%'])
        tokens = colors()
        for widget in (combo.view(), entry):
            palette = widget.palette()
            assert palette.color(QPalette.Base).name().lower() == tokens['Surface'].lower()
            assert palette.color(QPalette.Text).name().lower() == tokens['Text'].lower()
            assert palette.color(QPalette.HighlightedText).name().lower() == tokens['OnPrimary'].lower()
        entry.setEnabled(False)
        palette = entry.palette()
        foreground = palette.color(QPalette.Disabled, QPalette.Text)
        background = palette.color(QPalette.Disabled, QPalette.Base)
        assert foreground != background
        if app.platformName() == 'windows':
            assert app.styleHints().colorScheme() == Qt.ColorScheme.Light
    finally:
        for widget in widgets:
            widget.close()
        app.styleHints().setColorScheme(scheme)
        app.setPalette(previous)
