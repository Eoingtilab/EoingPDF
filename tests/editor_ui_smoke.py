"""Windows screenshots and real GPU input using generated documents only."""
import sys
from pathlib import Path
from unittest.mock import patch
import pymupdf as pdf
from PIL import Image, ImageDraw
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QFontDatabase, QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.app import STYLE
from eoingpdf.viewer import PdfViewer, SlideShow
from eoingpdf.stamp_editor import StampEditor
from eoingpdf.localization import install_language


def main():
    app = QApplication.instance() or QApplication([])
    install_language(app, 'ko-KR')
    app.setStyleSheet(STYLE)
    QFontDatabase.addApplicationFont(str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
    app.setFont(QFont('Pretendard', 10))
    folder = ROOT / 'temp/editor-ui-validation'
    folder.mkdir(parents=True, exist_ok=True)
    source, image = folder / 'original.pdf', folder / 'seal.jpg'
    with pdf.open() as document:
        page = document.new_page(width=595, height=842)
        page.insert_font(fontname='review', fontfile=str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
        page.insert_text((45, 70), '직인 배치 미리보기', fontname='review', fontsize=24)
        page.insert_text((45, 120), '저장 전에 위치와 크기를 확인합니다.', fontname='review', fontsize=13)
        page.draw_rect(pdf.Rect(45, 450, 550, 650), color=(.7, .75, .8))
        page.insert_text((340, 540), '확인자 서명 / 직인', fontname='review', fontsize=13)
        document.save(source)
    original = source.read_bytes()
    sample = Image.new('RGB', (180, 180), 'white')
    draw = ImageDraw.Draw(sample)
    draw.ellipse((15, 15, 164, 164), outline=(190, 0, 0), width=10)
    draw.text((65, 75), 'TEST', fill=(190, 0, 0), stroke_width=1)
    sample.save(image, quality=98)
    viewer = PdfViewer(source)
    viewer.resize(1180, 880)
    viewer.show()
    QTest.qWait(120)
    viewer.stamp_editor = editor = StampEditor(viewer)
    editor.add_image(image)
    editor.selected.x, editor.selected.y, editor.selected.width = 360, 550, 100
    editor.changed()
    QTest.qWait(80)
    scale = viewer.canvas.width() / viewer.visible_page_size[0]
    viewer.scroll.ensureVisible(round(410 * scale), round(600 * scale), 150, 150)
    QTest.qWait(20)
    assert viewer.stamp_button.geometry().right() < viewer.more_features_button.geometry().left()
    assert viewer.close_button.geometry().right() < viewer.width()
    viewer.grab().save(str(folder / 'stamp-on-current-pdf.png'))
    viewer.stamp_editor.reset()
    viewer.dirty = False
    viewer.close()

    slides = SlideShow(source)
    slides.resize(1180, 880)
    slides.show()
    QTest.qWait(100)
    slides.select_ink_tool('pen')
    QTest.qWait(50)
    controller = slides.canvas.native_ink
    if controller and controller.native:
        width, height = controller.native.size
        controller.on_input(0x0201, width * .15, height * .3)
        controller.on_input(0x0200, width * .75, height * .3)
        controller.on_input(0x0202, width * .75, height * .3)
        assert len(slides.canvas.ink_strokes) == 1
        slides.select_ink_tool('erase')
        controller.on_input(0x0201, width * .45, height * .3)
        controller.on_input(0x0202, width * .45, height * .3)
        assert len(slides.canvas.ink_strokes) == 2
        slides.canvas.undo_ink()
        assert len(slides.canvas.ink_strokes) == 1
        print('PASS real Windows GPU input: pen, partial eraser and undo', flush=True)
        # Qt screenshots omit the external GPU HWND; use the existing Qt renderer
        # for this client-pixel screenshot after the real GPU input checks.
        controller.hide()
        controller.disabled = True
    slides.ink_toolbar.insert(QImage(str(image)))
    slides.canvas.ink_strokes[-1][:] = [QPointF(.15, .58), QPointF(.45, .79)]
    slides.canvas.selected_ink = slides.canvas.ink_strokes[-1]
    slides.canvas.update()
    QTest.qWait(100)
    for button in slides.ink_toolbar.buttons.values():
        assert button.geometry().right() <= slides.ink_toolbar.width()
        assert button.geometry().bottom() <= slides.ink_toolbar.height()
    slides.grab().save(str(folder / 'expanded-ink-tools.png'))
    slides.canvas.clear_ink()
    slides.ink_by_slide.clear()
    slides.boards.clear()
    with patch('eoingpdf.viewer.QMessageBox.question', return_value=0):
        slides.close()
    assert source.read_bytes() == original
    assert not slides.ink_toolbar.snipper.timer.isActive()
    print('PASS Windows editor toolbar, in-canvas stamp preview, picture selection, bounded tools and original preservation', flush=True)


if __name__ == '__main__':
    main()
