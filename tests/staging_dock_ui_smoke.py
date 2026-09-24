"""Capture the real Windows Qt dock in three languages and two themes."""
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'windows'
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.localization import install_language
from eoingpdf.sdk_theme import install_theme
from eoingpdf.staging_dock import StagingDock


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    output = ROOT / 'temp/staging-dock-ui'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dock-ui-', dir=ROOT / 'temp') as name:
        folder = Path(name)
        settings = QSettings(str(folder / 'test.ini'), QSettings.IniFormat)
        controller = install_theme(app, settings)
        source = folder / '회의 자료 · Meeting notes · 会議資料.pdf'
        with pdf.open() as doc:
            doc.new_page()
            doc.save(source)
        reports = []
        for locale in ('ko-KR', 'en-US', 'ja-JP'):
            install_language(app, locale)
            for mode in ('light', 'dark'):
                controller.set_preference(mode)
                dock = StagingDock()
                dock.add_files([source])
                dock.show()
                QTest.qWait(150)
                assert dock.isVisible() and dock.files.count() == 1
                assert dock.geometry().width() < 600 and dock.geometry().height() < 600
                assert dock.merge_button.isEnabled()
                target = output / (locale + '-' + mode + '.png')
                assert dock.grab().save(str(target))
                reports.append(dict(locale=locale, theme=mode, width=dock.width(), height=dock.height()))
                dock.close()
                assert not dock.snap_timer.isActive()
        (output / 'report.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print('PASS: Windows floating dock, 3 languages x 2 themes, bounded window and stopped timers')


if __name__ == '__main__':
    main()
