from pathlib import Path
import sys

import pymupdf as pdf
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.viewer import SlideShow
from eoingpdf.ink_text import text_strokes
from eoingpdf.presentation_ink import save_presentation_ink
import eoingpdf.viewer as viewer_module


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('dark', [False, True])
def test_live_korean_input_color_and_rotated_save(tmp_path, monkeypatch, rotation, dark):
    app = QApplication.instance() or QApplication([])
    source, target = tmp_path / 'source.pdf', tmp_path / 'typed.pdf'
    with pdf.open() as document:
        page = document.new_page(width=400, height=300)
        if dark:
            page.draw_rect(page.rect, color=None, fill=(0, 0, 0))
        page.set_rotation(rotation)
        document.new_page()
        document.save(source)
    original = source.read_bytes()
    monkeypatch.setattr(viewer_module.QFileDialog, 'getSaveFileName', lambda *a, **k: (str(target), ''))
    monkeypatch.setattr(viewer_module.QMessageBox, 'information', lambda *a: None)
    errors = []
    monkeypatch.setattr(viewer_module.QMessageBox, 'warning', lambda *a: errors.append(a))
    slides = SlideShow(source)
    slides.resize(1000, 750)
    slides.show()
    app.processEvents()
    try:
        QTest.keyClick(slides, Qt.Key_T)
        rect = slides.canvas.page_rect()
        position = QPointF(rect.left() + rect.width() * .15, rect.top() + rect.height() * .15).toPoint()
        QTest.mouseClick(slides.canvas, Qt.LeftButton, pos=position)
        editor = slides.canvas.text_editor
        assert editor.isVisible()
        assert slides.canvas._text_color == ((1, 1, 1) if dark else (0, 0, 0))
        ime = QInputMethodEvent()
        ime.setCommitString('어잉PDF O')
        app.sendEvent(editor, ime)
        assert editor.text() == '어잉PDF O'
        QTest.keyClick(editor, Qt.Key_Return)
        assert not editor.isVisible()
        assert slides.index == 0
        strokes = slides.canvas.ink_strokes
        assert strokes and all(stroke.kind == 'text' and stroke.fill for stroke in strokes)
        count = len(strokes)
        assert slides.bake_annotations(), errors
        with pdf.open(target) as document:
            page = document[0]
            annotations = list(page.annots())
            assert len(annotations) == count
            assert all(annotation.type[0] == pdf.PDF_ANNOT_POLYGON for annotation in annotations)
            assert any(annotation.info['content'] == '어잉PDF O' for annotation in annotations)
            for annotation in annotations:
                assert tuple(annotation.colors['fill']) == ((1, 1, 1) if dark else (0, 0, 0))
            raster = page.get_pixmap(alpha=False)
            assert min(raster.samples) < max(raster.samples)
        assert source.read_bytes() == original
    finally:
        slides.canvas.text_editor.hide()
        slides.ink_by_slide.clear()
        slides.canvas.clear_ink()
        slides.close()
        app.processEvents()


def test_glyph_hole_and_wrapping_preserved_in_pdf(tmp_path):
    app = QApplication.instance() or QApplication([])
    source, target = tmp_path / 'source.pdf', tmp_path / 'text.pdf'
    with pdf.open() as document:
        document.new_page(width=400, height=300)
        document.save(source)
    strokes = text_strokes('O', QPointF(.2, .2), (400, 300), (0, 0, 0))
    save_presentation_ink(source, target, [0], {0: strokes})
    points = [point for stroke in strokes for point in stroke]
    cx = (min(p.x() for p in points) + max(p.x() for p in points)) * 200
    cy = (min(p.y() for p in points) + max(p.y() for p in points)) * 150
    with pdf.open(target) as document:
        pixmap = document[0].get_pixmap(matrix=pdf.Matrix(3, 3), alpha=False)
        assert pixmap.pixel(round(cx * 3), round(cy * 3)) == (255, 255, 255)
        assert min(pixmap.samples) == 0
    wrapped = text_strokes('한글 테스트 ' * 8, QPointF(.4, .1), (200, 300), (0, 0, 0))
    assert max(p.y() for stroke in wrapped for p in stroke) > .3
    with pytest.raises(ValueError, match='벗어'):
        text_strokes('텍스트 ' * 30, QPointF(.1, .8), (100, 100), (0, 0, 0))


def test_margin_double_click_cancels_navigation_and_escape_cancels_text(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'source.pdf'
    with pdf.open() as document:
        document.new_page()
        document.new_page()
        document.save(source)
    slides = SlideShow(source)
    slides.resize(1000, 750)
    slides.show()
    app.processEvents()
    try:
        point = slides.canvas.page_rect().center().toPoint()
        QTest.mouseClick(slides.canvas, Qt.LeftButton, pos=point)
        assert slides.click_timer.isActive()
        QTest.mouseDClick(slides.canvas, Qt.LeftButton, pos=point)
        assert slides.canvas.text_editor.isVisible()
        assert not slides.click_timer.isActive()
        slides.canvas.text_editor.setText('취소할 텍스트')
        QTest.keyClick(slides.canvas.text_editor, Qt.Key_Escape)
        assert not slides.canvas.text_editor.isVisible() and not slides.has_ink()
        assert slides.index == 0
        QTest.mouseClick(slides.canvas, Qt.LeftButton, pos=point)
        QTest.qWait(app.styleHints().mouseDoubleClickInterval() + 40)
        assert slides.index == 1
    finally:
        slides.canvas.text_editor.hide()
        slides.canvas.clear_ink()
        slides.close()
        app.processEvents()


def test_overflow_keeps_draft_and_blocks_page_change(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'source.pdf'
    with pdf.open() as document:
        document.new_page(width=100, height=100)
        document.new_page()
        document.save(source)
    slides = SlideShow(source)
    slides.resize(1000, 750)
    slides.show()
    app.processEvents()
    try:
        rect = slides.canvas.page_rect()
        slides.canvas.begin_text(QPointF(rect.left() + rect.width() * .1, rect.top() + rect.height() * .8))
        editor = slides.canvas.text_editor
        editor.setText('너무 긴 텍스트를 입력하는 검사입니다' * 5)
        QTest.keyClick(editor, Qt.Key_Return)
        assert editor.isVisible() and slides.canvas.text_error.isVisible()
        slides.advance(1)
        assert slides.index == 0 and editor.text()
        QTest.keyClick(editor, Qt.Key_Escape)
        assert not slides.canvas.text_error.isVisible()
        slides.advance(1)
        assert slides.index == 1
    finally:
        slides.canvas.text_editor.hide()
        slides.canvas.clear_ink()
        slides.close()
        app.processEvents()
