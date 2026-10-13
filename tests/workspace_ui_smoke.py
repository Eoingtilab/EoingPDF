"""Inspect the task-oriented workspace on Windows using synthetic PDFs only."""
import sys
from pathlib import Path
from unittest.mock import patch
import pymupdf as pdf
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.app import STYLE
from eoingpdf.viewer import PdfViewer
from eoingpdf.viewer_workspace import HistoryDialog
from eoingpdf.tool_browser import ToolBrowser
from eoingpdf.sdk_theme import install_theme, apply_style
from eoingpdf.localization import install_language
from eoingpdf.advanced_ui import AdvancedDialog


def contained(widget, parent):
    position = widget.mapTo(parent, QPoint())
    assert parent.rect().contains(position), widget.objectName()
    assert parent.rect().contains(position + QPoint(widget.width() - 1, widget.height() - 1)), widget.objectName()


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    folder = ROOT / 'temp/workspace-ui-validation'
    folder.mkdir(parents=True, exist_ok=True)
    theme = install_theme(app, QSettings(str(folder / 'theme.ini'), QSettings.IniFormat))
    apply_style(app, STYLE)
    source = folder / 'ui-sample.pdf'
    with pdf.open() as document:
        for number in range(2):
            page = document.new_page(width=595, height=842)
            page.insert_font(fontname='sample', fontfile=str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
            page.insert_text((45, 70), 'PDF 작업 공간', fontname='sample', fontsize=26)
            page.insert_text((45, 110), '발표와 직인, 편집을 한 화면에서 편하게', fontname='sample', fontsize=14)
            page.draw_rect(pdf.Rect(45, 250, 550, 450), color=(.7, .75, .8))
            page.insert_text((60, 295), f'검토 자료 {number + 1}', fontname='sample', fontsize=18)
        document.save(source)
    original = source.read_bytes()
    from PIL import Image, ImageDraw
    seal = folder / 'seal.jpg'
    sample = Image.new('RGB', (90, 90), 'white')
    ImageDraw.Draw(sample).ellipse((9, 9, 81, 81), outline='red', width=5)
    sample.save(seal)
    with patch('eoingpdf.license_ui.ensure_license', return_value=True):
        for locale in ('ko-KR', 'en-US', 'ja-JP'):
            install_language(app, locale)
            for mode in ('light', 'dark'):
                theme.set_preference(mode)
                viewer = PdfViewer(source)
                viewer.show()
                for width, height in ((960, 820), (680, 480)):
                    viewer.resize(width, height)
                    QTest.qWait(60)
                    assert viewer.size().width() == width
                    assert viewer.scroll.height() > 120
                    for widget in (viewer.open_button, viewer.slideshow_button, viewer.stamp_button,
                                   viewer.more_features_button, viewer.save_button, viewer.close_button,
                                   viewer.undo_button, viewer.redo_button, viewer.history_button,
                                   viewer.form_button, viewer.page_tools_button, viewer.view_tools_button,
                                   viewer.page, viewer.zoom, viewer.print_button):
                        contained(widget, viewer)
                    viewer.grab().save(str(folder / f'workspace-{locale}-{mode}-{width}.png'))
                viewer.move_current_page(1)
                assert viewer.undo_button.isEnabled()
                viewer.undo_button.click()
                assert viewer.pages == [0, 1] and viewer.redo_button.isEnabled()
                viewer.redo_button.click()
                history = HistoryDialog(viewer)
                history.show()
                QTest.qWait(30)
                assert history.entries.count() == 2
                history.grab().save(str(folder / f'history-{locale}-{mode}.png'))
                history.reject()
                tools = ToolBrowser(viewer)
                tools.resize(480, 380)
                tools.show()
                tools.search.setText('watermark')
                QTest.qWait(30)
                assert tools.results.count() == 2
                for widget in (tools.search, tools.category, tools.results, tools.open_button, tools.close_button):
                    contained(widget, tools)
                tools.grab().save(str(folder / f'tools-{locale}-{mode}.png'))
                tools.reject()
                viewer.reset_edits()
                from eoingpdf.stamp_editor import StampEditor
                viewer.stamp_editor = StampEditor(viewer)
                viewer.stamp_editor.add_image(seal)
                QTest.qWait(30)
                assert viewer.width() == 680
                contained(viewer.stamp_editor.panel, viewer)
                viewer.grab().save(str(folder / f'stamp-{locale}-{mode}-680.png'))
                viewer.reset_edits()
                if locale == 'ko-KR' and mode == 'dark':
                    dialog = AdvancedDialog(viewer)
                    dialog.source.setText(str(source))
                    dialog.tool.setCurrentIndex(dialog.tool.findData('watermark_text'))
                    dialog.watermark_text.setText('검토용')
                    dialog.show()
                    QTest.qWait(30)
                    assert dialog.preview_button.isVisible() and not dialog.save.isVisible()
                    dialog.grab().save(str(folder / 'watermark-dialog.png'))
                    dialog.reject()
                viewer.close()
    assert source.read_bytes() == original
    print('PASS workspace: 3 languages, 2 themes, 2 sizes; tools, history, undo/redo and source protection')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
