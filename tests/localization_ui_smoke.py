"""Capture localized tools and verify that controls fit actual Windows windows."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'windows'
import pymupdf as pdf
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QComboBox, QLineEdit, QWidget, QScrollArea

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.advanced_ui import AdvancedDialog
from eoingpdf.app import STYLE
from eoingpdf.diff_ui import DiffDialog
from eoingpdf.form_ui import FormDialog
from eoingpdf.localization import install_language
from eoingpdf.presenter import PresenterHud
from eoingpdf.sdk_theme import apply_style, install_theme
from eoingpdf.settings_ui import SettingsDialog
from eoingpdf.viewer import SlideShow


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    output = ROOT / 'temp/localization-ui'
    output.mkdir(exist_ok=True)
    reports = []
    with tempfile.TemporaryDirectory(prefix='localization-ui-', dir=ROOT / 'temp') as name:
        folder = Path(name)
        theme = install_theme(app, QSettings(str(folder / 'settings.ini'), QSettings.IniFormat))
        apply_style(app, STYLE)
        source = folder / 'Synthetic.pdf'
        with pdf.open() as document:
            page = document.new_page()
            page.insert_text((50, 140), 'Synthetic content - preserved in every language.')
            field = pdf.Widget()
            field.field_name, field.field_value = 'Document label', 'Document value'
            field.field_type, field.rect = pdf.PDF_WIDGET_TYPE_TEXT, pdf.Rect(50, 50, 350, 80)
            page.add_widget(field)
            document.new_page().insert_text((50, 50), 'Next slide')
            document.save(source)
        original = source.read_bytes()

        def inspect(window, name, locale, mode):
            window.show()
            QTest.qWait(80)
            assert window.width() <= 1280 and window.height() <= 1000, (name, window.size())
            visible = 0
            for widget in window.findChildren(QWidget):
                if not isinstance(widget, (QLabel, QPushButton, QComboBox, QLineEdit)) or not widget.isVisibleTo(window):
                    continue
                visible += 1
                point = widget.mapTo(window, QPoint())
                parent = widget.parentWidget()
                scroll_child = False
                while parent is not None and parent is not window:
                    scroll_child = scroll_child or isinstance(parent, QScrollArea)
                    parent = parent.parentWidget()
                if not scroll_child:
                    assert window.rect().contains(point), (name, type(widget).__name__, point)
                if isinstance(widget, QPushButton):
                    assert widget.width() >= widget.fontMetrics().horizontalAdvance(widget.text().replace('&', '')) + 8, (name, widget.text(), widget.width())
                text = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
                if locale != 'ko-KR':
                    assert not re.search('[가-힣]', text), (name, text)
            assert window.grab().save(str(output / f'{locale}-{mode}-{name}.png'))
            reports.append(dict(locale=locale, theme=mode, window=name, width=window.width(), height=window.height(), controls=visible))

        for locale in ('ko-KR', 'en-US', 'ja-JP'):
            install_language(app, locale)
            for mode in ('light', 'dark'):
                theme.set_preference(mode)
                advanced = AdvancedDialog()
                for operation in ('encrypt', 'stamp', 'bates'):
                    advanced.tool.setCurrentIndex(advanced.tool.findData(operation))
                    inspect(advanced, 'advanced-' + operation, locale, mode)
                    assert advanced.height() <= 700, advanced.size()
                    assert advanced.rect().contains(advanced.save.geometry())
                advanced.close()
                advanced.deleteLater()
                for name, dialog in [('form', FormDialog(source, 0)), ('diff', DiffDialog()), ('settings', SettingsDialog())]:
                    if name == 'settings':
                        for index in range(dialog.tabs.count()):
                            dialog.tabs.setCurrentIndex(index)
                            inspect(dialog, name + '-' + str(index), locale, mode)
                    else:
                        inspect(dialog, name, locale, mode)
                    dialog.close()
                    dialog.deleteLater()
                audience = SlideShow(source)
                hud = PresenterHud(audience)
                inspect(hud, 'presenter', locale, mode)
                audience.close()
                hud.close()
                hud.deleteLater()
                audience.deleteLater()
                app.processEvents()
        assert source.read_bytes() == original
    (output / 'report.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print(f'PASS: {len(reports)} Windows localized UI captures, visible controls and original PDF preserved')


if __name__ == '__main__':
    main()
