"""Windows Qt reader reliability gate; only grab this test's own widgets."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

if sys.platform != 'win32':
    raise SystemExit('This gate requires the actual Windows Qt platform.')
os.environ['QT_QPA_PLATFORM'] = 'windows'

import pymupdf as pdf
from PIL import Image, ImageDraw
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractItemView, QMessageBox, QPushButton, QWidget
from shiboken6 import isValid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.app import STYLE
from eoingpdf.ink_stroke import InkStroke
from eoingpdf.localization import install_language
from eoingpdf.sdk_theme import apply_style, install_theme
from eoingpdf.stamp_editor import StampEditor
from eoingpdf.viewer import PdfViewer, SlideShow, THUMBNAIL_CARD_LIMIT


def flush():
    QApplication.instance().processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def fixture(path):
    if path.exists():
        return
    with pdf.open() as document:
        for index in range(50):
            page = document.new_page(width=420, height=560)
            page.insert_text((45, 70), 'Daily office PDF verification', fontsize=20)
            page.insert_text((45, 115), f'GENERATED OFFICE PAGE {index + 1:02} / 50', fontsize=16)
            page.draw_rect(pdf.Rect(45, 170, 370, 230), color=(.5, .6, .75))
            field = pdf.Widget()
            field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            field.field_name = f'office-{index + 1}'
            field.field_value = f'ORIGINAL {index + 1}'
            field.rect = pdf.Rect(50, 180, 365, 210)
            page.add_widget(field)
            if index % 7 == 0:
                page.set_rotation(90)
        document.save(path)


def grab(widget, target):
    assert widget.isVisible()
    assert widget.grab().save(str(target)), target


def main():
    app = QApplication.instance() or QApplication([])
    assert app.platformName() == 'windows', app.platformName()
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    install_language(app, 'ko-KR')
    folder = ROOT / 'temp/reliability'
    folder.mkdir(parents=True, exist_ok=True)
    theme = install_theme(app, QSettings(str(folder / 'reliability-ui-theme.ini'), QSettings.IniFormat))
    theme.set_preference('dark')
    apply_style(app, STYLE)
    source = folder / 'windows-reader-50-pages.pdf'
    fixture(source)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    seal_path = folder / 'windows-reader-seal.jpg'
    if not seal_path.exists():
        image = Image.new('RGB', (100, 100), 'white')
        ImageDraw.Draw(image).ellipse((8, 8, 92, 92), outline=(205, 0, 0), width=7)
        image.save(seal_path, quality=95)
    owner = QWidget()
    viewer = None
    slides = None
    report = {'platform': app.platformName(), 'pages': 50, 'original_sha256': original,
              'scope': 'Actual Windows Qt widgets; generated PDF/JPEG only; no desktop or other-app screenshots.'}
    with patch('eoingpdf.sniffer_ui.MicroSniffer.start'), \
            patch('eoingpdf.license_ui.ensure_license', return_value=True), \
            patch('eoingpdf.viewer.QMessageBox.question', return_value=QMessageBox.Discard) as viewer_question:
        try:
            viewer = PdfViewer(source, owner)
            viewer.resize(960, 820)
            viewer.show()
            QTest.qWait(100)
            assert not viewer.canvas.pixmap().isNull()

            viewer.page.setValue(16)
            QTest.mouseClick(viewer.next, Qt.LeftButton)
            assert viewer.page.value() == 17
            QTest.mouseClick(viewer.previous, Qt.LeftButton)
            assert viewer.page.value() == 16
            arrows = {button.text(): button for button in viewer.findChildren(QPushButton)
                      if button.text() in ('▲', '▼')}
            QTest.mouseClick(arrows['▼'], Qt.LeftButton)
            assert viewer.page.value() == 17
            QTest.mouseClick(arrows['▲'], Qt.LeftButton)
            assert viewer.page.value() == 16
            viewer.page.setFocus()
            viewer.page.selectAll()
            QTest.keyClicks(viewer.page, '23')
            QTest.keyClick(viewer.page, Qt.Key_Return)
            assert viewer.page.value() == 23 and viewer.isVisible()
            assert not viewer.dirty and not viewer.edit_history.can_undo
            viewer.page.setValue(1)
            assert not viewer.previous.isEnabled()
            viewer.page.setValue(50)
            assert not viewer.next.isEnabled()
            report['navigation_and_enter_verified'] = True

            maximum_cards = 0
            for row in range(0, viewer.count, 3):
                viewer.thumbnails.scrollToItem(viewer.thumbnails.item(row), QAbstractItemView.PositionAtTop)
                for _ in range(3):
                    viewer.fill_thumbnails()
                flush()
                cards = sum(viewer.thumbnails.itemWidget(viewer.thumbnails.item(index)) is not None
                            for index in range(viewer.count))
                maximum_cards = max(maximum_cards, cards)
                assert cards <= THUMBNAIL_CARD_LIMIT and len(viewer.thumbnail_cache) <= THUMBNAIL_CARD_LIMIT
            viewer.page.setValue(23)
            ready_by = time.monotonic() + 1
            while viewer.thumbnails.itemWidget(viewer.thumbnails.currentItem()) is None and time.monotonic() < ready_by:
                QTest.qWait(20)
            current_card = viewer.thumbnails.itemWidget(viewer.thumbnails.currentItem())
            assert current_card is not None, 'The selected page thumbnail must load after navigating.'
            assert not current_card.findChild(QPushButton, 'thumbnailPage').icon().isNull()
            QTest.qWait(30)
            grab(viewer, folder / 'windows-reader-50-pages.png')
            report['maximum_live_thumbnail_cards'] = maximum_cards

            # Match the production parent-close flow, but keep the presentation
            # windowed so this gate does not move to another monitor.
            viewer.stamp_editor = StampEditor(viewer)
            viewer.stamp_editor.add_image(seal_path)
            draft_path = viewer.stage_current_preview(display=False)
            slides = SlideShow(draft_path, viewer.page.value() - 1, viewer)
            viewer.slideshow = slides
            slides.viewer_draft_path = draft_path
            slides.finished.connect(lambda _: viewer.finish_slideshow(slides))
            slides.resize(960, 700)
            slides.show()
            QTest.qWait(80)
            slides.canvas.set_ink([InkStroke([QPointF(.1, .3), QPointF(.5, .3)], 'pen')])
            before = viewer.capture_edit_state()
            viewer_question.reset_mock()
            prompts = []
            prompt_errors = []
            prompt_timer = QTimer()
            attempts = 0

            def click_cancel():
                nonlocal attempts
                attempts += 1
                prompt = next((widget for widget in app.topLevelWidgets()
                               if isinstance(widget, QMessageBox) and widget.parentWidget() is slides
                               and widget.isVisible()), None)
                if prompt is not None:
                    cancel = next((button for button in prompt.buttons()
                                   if prompt.buttonRole(button) == QMessageBox.RejectRole), None)
                    if cancel is not None:
                        prompts.append(prompt.windowTitle())
                        QTest.mouseClick(cancel, Qt.LeftButton)
                        prompt_timer.stop()
                        return
                if attempts >= 100:
                    prompt_errors.append('Presentation cancel button did not appear.')
                    prompt_timer.stop()
                    active_prompt = prompt or app.activeModalWidget()
                    if isinstance(active_prompt, QMessageBox):
                        active_prompt.reject()

            prompt_timer.timeout.connect(click_cancel)
            prompt_timer.start(20)
            try:
                assert not viewer.close()
            finally:
                prompt_timer.stop()
            assert prompts and not prompt_errors and viewer_question.call_count == 0
            assert viewer.isVisible() and slides.isVisible() and slides.has_ink()
            assert viewer.capture_edit_state() == before and draft_path.exists()
            assert viewer.stamp_editor.stamps and viewer.undo_button.isEnabled()
            QTest.qWait(40)
            grab(viewer, folder / 'windows-reader-after-presentation-cancel.png')
            grab(slides, folder / 'windows-presentation-after-cancel.png')
            report['actual_presentation_cancel_button_clicked'] = True
            report['viewer_draft_stamp_ink_and_temporary_pdf_preserved'] = True

            slides.canvas.set_ink([])
            slides.ink_by_slide.clear()
            slides.boards.clear()
            slides.reject()
            QTest.qWait(40)
            assert not slides.isVisible()
            viewer.fit_timer.start(20)
            assert viewer.close()
            flush()
            QTest.qWait(60)
            assert isValid(viewer) and viewer.parent() is owner
            assert not viewer.isVisible() and viewer.thumbnails.count() == 0 and not viewer.thumbnail_cache
            assert viewer.canvas.pixmap().isNull()
            assert not viewer.fit_timer.isActive() and not viewer.thumbnail_timer.isActive()
            assert not viewer.feedback_timer.isActive()
            assert not draft_path.exists()
            report['accepted_close_releases_rasters_timers_and_temporary_pdf'] = True
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original
            report['original_unchanged'] = True
            (folder / 'windows-reliability-ui.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report), flush=True)
            print('PASS Windows reader: 50 pages, navigation, 24-card bound, real Cancel button, draft preservation, close cleanup.', flush=True)
        finally:
            if slides is not None:
                slides.canvas.set_ink([])
                slides.ink_by_slide.clear()
                slides.boards.clear()
                slides.reject()
            if viewer is not None:
                viewer.close()
            owner.close()
            owner.deleteLater()
            flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
