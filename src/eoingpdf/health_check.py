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
        from PySide6.QtWidgets import QApplication
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
                doc.save(source)
            window = PdfViewer(source)
            try:
                window.render()
                if window.canvas.pixmap().isNull():
                    raise RuntimeError(tr('PDF 화면을 렌더링하지 못했습니다.'))
            finally:
                window.close()
                window.deleteLater()
                app.processEvents()
        # Exclusive output prevents accepting a pre-existing success report.
        with report.open('x', encoding='utf-8') as stream:
            json.dump({'ok': True, 'nonce': nonce}, stream)
        return 0
    except Exception:
        return 1
