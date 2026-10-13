"""Isolated post-update runtime check; no licensing, network or user documents."""
from .localization import tr
import json
import os
from pathlib import Path
import tempfile


def main(arguments):
    if len(arguments) not in (2, 4):
        return 2
    report, nonce = Path(arguments[0]), arguments[1]
    try:
        if len(arguments) == 4:
            from .updates import current_version, version_tuple
            from .distribution import is_onefile
            if (arguments[3] != 'onefile' or not is_onefile()
                    or version_tuple(current_version()) != version_tuple(arguments[2])):
                return 1
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        import pymupdf as pdf
        from PySide6.QtWidgets import QApplication, QPushButton
        from PySide6.QtGui import QFontDatabase
        from .app import ROOT
        from .viewer import PdfViewer
        app = QApplication.instance() or QApplication([])
        font = QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
        if font < 0:
            raise RuntimeError(tr('필수 폰트를 불러오지 못했습니다.'))
        with tempfile.TemporaryDirectory(prefix='eoing-health-') as folder:
            source = Path(folder) / 'probe.pdf'
            with pdf.open() as doc:
                doc.new_page().insert_text((72, 72), 'EoingPDF runtime check')
                doc.new_page().insert_text((72, 72), 'Next page')
                doc.save(source)
            window = PdfViewer(source)
            try:
                window.render()
                if window.canvas.pixmap().isNull():
                    raise RuntimeError(tr('PDF 화면을 렌더링하지 못했습니다.'))
                next(button for button in window.findChildren(QPushButton) if button.text() == '▼').click()
                assert window.page.value() == 2
                next(button for button in window.findChildren(QPushButton) if button.text() == '▲').click()
                assert window.page.value() == 1
                # Check the same JPEG decoder and editor modules used after an
                # update. All input/output remains inside this synthetic probe.
                from PIL import Image, ImageDraw
                from PySide6.QtGui import QImageReader
                from .stamp_editor import StampEditor
                picture = Path(folder) / 'seal.jpg'
                sample = Image.new('RGB', (100, 80), 'white')
                ImageDraw.Draw(sample).rectangle((10, 10, 89, 69), outline='red', width=8)
                sample.save(picture, quality=95)
                editor = window.stamp_editor = StampEditor(window)
                editor.add_image(picture)
                with pdf.open(source) as probe:
                    editor.apply(probe, [0])
                    assert probe[0].get_images()
                assert window.undo_edit() and not editor.stamps and not window.dirty
                assert window.redo_edit() and len(editor.stamps) == 1 and window.dirty
                from .tool_browser import ToolBrowser
                tools = ToolBrowser(window)
                tools.search.setText('watermark')
                assert tools.results.count() == 2
                tools.reject()
                tools.deleteLater()
                from .viewer import SlideShow
                slides = SlideShow(source)
                try:
                    assert slides.ink_toolbar.insert(QImageReader(str(picture)).read()), 'JPEG decoder missing'
                    slides.canvas.undo_ink()
                    assert not slides.canvas.ink_strokes
                    slides.canvas.redo_ink()
                    assert slides.canvas.ink_strokes[0].kind == 'image'
                finally:
                    slides.canvas.set_ink([])
                    slides.ink_by_slide.clear()
                    slides.boards.clear()
                    slides.close()
                    slides.deleteLater()
            finally:
                if window.stamp_editor:
                    window.stamp_editor.reset()
                    window.dirty = False
                window.close()
                window.deleteLater()
                app.processEvents()
        # Exclusive output prevents accepting a pre-existing success report.
        with report.open('x', encoding='utf-8') as stream:
            json.dump({'ok': True, 'nonce': nonce}, stream)
        return 0
    except Exception:
        return 1
