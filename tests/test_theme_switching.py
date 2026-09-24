import sys
import time
from pathlib import Path

import pymupdf as pdf
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLineEdit, QVBoxLayout, QPushButton

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf import sdk_theme


@pytest.fixture
def theme(tmp_path):
    app = QApplication.instance()
    palette, style = app.palette(), app.styleSheet()
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat)
    controller = sdk_theme.install_theme(app, settings)
    try:
        yield controller
    finally:
        app.styleHints().colorSchemeChanged.disconnect(controller.system_changed)
        del app.eoing_theme
        sdk_theme._styles.pop(app, None)
        app.styleHints().setColorScheme(Qt.ColorScheme.Unknown)
        app.setStyleSheet(style)
        app.setPalette(palette)
        controller.deleteLater()


def contrast(a, b):
    def luminance(value):
        rgb = QColor(value).getRgbF()[:3]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    values = sorted((luminance(a), luminance(b)))
    return (values[1] + .05) / (values[0] + .05)


def test_dark_semantic_colors_keep_readable_controls():
    tokens = sdk_theme.theme_colors('dark')
    for surface in ('AppBackground', 'Surface', 'SurfaceSoft', 'SurfaceHover', 'SurfaceSelected'):
        for text in ('Text', 'TextStrong'):
            assert contrast(tokens[text], tokens[surface]) >= 4.5
    assert contrast(tokens['OnPrimary'], tokens['Primary']) >= 4.5
    assert contrast(tokens['TextMuted'], tokens['Surface']) >= 4.5
    assert contrast(tokens['Focus'], tokens['SurfaceSelected']) >= 4.5


def test_live_switch_updates_existing_controls_and_new_popups(theme):
    app = QApplication.instance()
    from eoingpdf.app import STYLE
    sdk_theme.apply_style(app, STYLE)
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    entry, combo = QLineEdit('PDF'), QComboBox()
    navigation = QPushButton('문서 합치기')
    navigation.setObjectName('nav')
    navigation.setCheckable(True)
    navigation.setChecked(True)
    combo.addItems(['너비 맞춤', '100%'])
    layout.addWidget(entry)
    layout.addWidget(combo)
    layout.addWidget(navigation)
    sdk_theme.apply_style(dialog, 'QDialog {background:#f7f9fc;} QLineEdit {background:white;color:#263246;}')
    dialog.show()
    try:
        for mode in ('dark', 'light', 'dark'):
            theme.set_preference(mode)
            app.processEvents()
            tokens = sdk_theme.theme_colors(mode)
            assert theme.settings.value('appearance/theme') == mode
            assert tokens['AppBackground'].lower() in dialog.styleSheet().lower()
            assert tokens['Surface'].lower() in dialog.styleSheet().lower()
            assert entry.palette().color(QPalette.Text).name() == tokens['Text'].lower()
            assert contrast(entry.palette().color(QPalette.Text), entry.palette().color(QPalette.Base)) >= 4.5
            assert contrast(navigation.palette().color(QPalette.ButtonText), navigation.palette().color(QPalette.Button)) >= 4.5
            combo.showPopup()
            app.processEvents()
            assert contrast(combo.view().palette().color(QPalette.Text), combo.view().palette().color(QPalette.Base)) >= 4.5
            combo.hidePopup()
        with pytest.raises(ValueError):
            theme.set_preference('invalid')
    finally:
        dialog.close()
        dialog.deleteLater()


def test_system_signal_updates_only_system_preference(theme, monkeypatch):
    hints = QApplication.instance().styleHints()
    theme.set_preference('system')
    monkeypatch.setattr(hints, 'colorScheme', lambda: Qt.ColorScheme.Dark)
    hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert theme.mode == 'dark'
    assert theme.settings.value('appearance/theme') == 'system'
    theme.set_preference('light')
    hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert theme.mode == 'light'


def test_pdf_pixels_unchanged_when_viewer_theme_changes(theme, tmp_path):
    from eoingpdf.viewer import PdfViewer
    from eoingpdf.app import STYLE
    app = QApplication.instance()
    sdk_theme.apply_style(app, STYLE)
    path = tmp_path / 'page.pdf'
    with pdf.open() as document:
        page = document.new_page()
        page.draw_rect((20, 20, 200, 200), fill=(1, 0, 0))
        document.save(path)
    original = path.read_bytes()
    viewer = PdfViewer(path)
    viewer.show()
    # Fit-width rendering and asynchronous diagnostics can both resize the
    # viewport after show(). Compare at the settled size, not after a fixed nap.
    deadline = time.monotonic() + 5
    stable = 0
    previous_size = None
    while time.monotonic() < deadline and stable < 3:
        QTest.qWait(50)
        size = viewer.scroll.viewport().size()
        quiet = viewer.sniffer.process is None and not viewer.fit_timer.isActive()
        stable = stable + 1 if quiet and size == previous_size else 0
        previous_size = size
    assert stable >= 3, 'Viewer did not finish initial layout and diagnostics'
    page_image = viewer.canvas.pixmap().toImage()
    try:
        for mode in ('dark', 'light'):
            theme.set_preference(mode)
            app.processEvents()
            assert viewer.zoom.currentIndex() == 0
            assert path.read_bytes() == original
            assert viewer.canvas.pixmap().toImage() == page_image
            assert sdk_theme.theme_colors(mode)['Text'].lower() in viewer.zoom.styleSheet().lower()
    finally:
        viewer.close()
        viewer.deleteLater()


def test_audience_chrome_keeps_contrast_fonts_and_document_pixels(theme, tmp_path):
    from eoingpdf.viewer import SlideShow
    from eoingpdf.app import STYLE
    app = QApplication.instance()
    sdk_theme.apply_style(app, STYLE)
    path = tmp_path / 'slides.pdf'
    with pdf.open() as document:
        page = document.new_page(width=640, height=360)
        page.draw_rect((20, 20, 200, 200), fill=(1, 0, 0))
        document.save(path)
    original = path.read_bytes()
    show = SlideShow(path)
    show.resize(1000, 700)
    show.show()
    QTest.qWait(100)
    original_style = show.styleSheet()
    original_pixels = show.canvas.pixmap().toImage()
    try:
        for mode in ('dark', 'light', 'dark', 'light'):
            theme.set_preference(mode)
            app.processEvents()
            assert show.styleSheet() == original_style
            assert show.exit_button.font().pixelSize() == 15
            assert contrast(show.hint.palette().color(QPalette.WindowText),
                            show.hint.palette().color(QPalette.Window)) >= 4.5
            for button in (show.presenter_button, show.ink_button, show.bake_button, show.exit_button):
                assert contrast(button.palette().color(QPalette.ButtonText),
                                button.palette().color(QPalette.Button)) >= 4.5
            show.ink_tools.showPopup()
            app.processEvents()
            popup = show.ink_tools.view().palette()
            assert contrast(popup.color(QPalette.Text), popup.color(QPalette.Base)) >= 4.5
            assert contrast(popup.color(QPalette.HighlightedText), popup.color(QPalette.Highlight)) >= 4.5
            show.ink_tools.hidePopup()
            assert show.canvas.pixmap().toImage() == original_pixels
            assert path.read_bytes() == original
    finally:
        show.close()
        show.deleteLater()
