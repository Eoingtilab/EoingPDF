import sys
from pathlib import Path
import pytest
import pymupdf as pdf
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox
from PySide6.QtGui import QFont, QFontDatabase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.localization import install_language
from eoingpdf.viewer import PdfViewer


@pytest.mark.parametrize('locale,open_text,fit_text', [
    ('ko-KR', 'PDF 열기', '너비 맞춤'),
    ('en-US', 'Open PDF', 'Fit width'),
    ('ja-JP', 'PDFを開く', '幅に合わせる'),
])
def test_translated_viewer_preserves_fit_zoom_and_page_controls(tmp_path, monkeypatch, locale, open_text, fit_text):
    app = QApplication.instance()
    previous = getattr(app, 'eoing_locale', 'ko-KR')
    previous_style, previous_font = app.styleSheet(), app.font()
    from eoingpdf.app import STYLE, ROOT
    app.setStyleSheet(STYLE)
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    path = tmp_path / 'source.pdf'
    with pdf.open() as document:
        document.new_page().insert_text((72, 72), 'First page')
        document.new_page().insert_text((72, 72), 'Second page')
        document.save(path)
    original = path.read_bytes()
    install_language(app, locale)
    viewer = PdfViewer(path)
    try:
        viewer.resize(680, 480)
        viewer.show()
        app.processEvents()
        assert viewer.width() == 680
        assert viewer.page.geometry().top() > viewer.scroll.geometry().bottom()
        for control in (viewer.close_button, viewer.page, viewer.previous, viewer.next, viewer.zoom):
            assert viewer.rect().contains(control.geometry())
        assert open_text in [button.text() for button in viewer.findChildren(QPushButton)]
        assert viewer.zoom.currentText() == fit_text
        viewer.render()
        assert viewer.canvas.pixmap() is not None and not viewer.canvas.pixmap().isNull()
        viewer.next.click()
        assert viewer.page.value() == 2 and viewer.zoom.currentText() == fit_text
        viewer.zoom.setCurrentIndex(3)
        viewer.render()
        assert viewer.zoom.currentText() == '100%'
        assert viewer.canvas.pixmap().width() == 595
        questions = []
        monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda parent: True)
        def decline(parent, title, message, *args):
            questions.append(message)
            return QMessageBox.No
        monkeypatch.setattr(QMessageBox, 'question', decline)
        viewer.stage_delete({0})
        expected = {'ko-KR': '1페이지를 삭제', 'en-US': 'Delete pages 1', 'ja-JP': '1ページを削除'}
        assert expected[locale] in questions[0]
        assert viewer.count == 2 and not viewer.dirty
        assert path.read_bytes() == original
    finally:
        viewer.close()
        install_language(app, previous)
        app.setStyleSheet(previous_style)
        app.setFont(previous_font)
