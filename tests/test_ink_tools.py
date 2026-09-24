import sys
import weakref
from pathlib import Path
from time import monotonic

import pymupdf as pdf
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.viewer import SlideShow
from eoingpdf.ink_stroke import InkStroke
import eoingpdf.viewer as viewer_module


def test_ghosts_expire_on_previous_slide_and_board_without_revisiting(tmp_path, monkeypatch):
    from eoingpdf import presentation_canvas
    clock = [100.0]
    monkeypatch.setattr(presentation_canvas, 'monotonic', lambda: clock[0])
    source = tmp_path / 'pages.pdf'
    with pdf.open() as document:
        document.new_page()
        document.new_page()
        document.save(source)
    slides = SlideShow(source)
    try:
        pen = InkStroke([QPointF(.1, .1), QPointF(.2, .2)])
        ghost = InkStroke(pen, 'ghost')
        ghost.created = clock[0]
        released = weakref.ref(ghost)
        slides.canvas.ink_strokes.extend([pen, ghost])
        del ghost
        slides.set_blank('black')
        board_ghost = InkStroke(pen, 'ghost')
        board_ghost.created = clock[0]
        board_released = weakref.ref(board_ghost)
        slides.canvas.ink_strokes.append(board_ghost)
        del board_ghost
        slides.advance(1)
        assert slides.canvas.ghost_timer.isActive()
        # Clearing an empty current slide must not stop cleanup of old surfaces.
        slides.canvas.clear_ink()
        assert slides.canvas.ghost_timer.isActive()
        clock[0] += 3.3
        slides.canvas.expire_ghosts()
        assert released() is not None and board_released() is not None
        clock[0] += .4
        slides.canvas.expire_ghosts()
        assert released() is None and board_released() is None
        assert slides.ink_by_slide[0] == [pen]
        assert slides.boards[(0, 'black')]['strokes'] == []
        assert not slides.canvas._ghost_surfaces
        assert not slides.canvas.ghost_timer.isActive()
    finally:
        slides.canvas.clear_ink()
        slides.ink_by_slide.clear()
        slides.boards.clear()
        slides.close()


def test_repeated_surface_switches_release_expired_stroke_objects(monkeypatch):
    from eoingpdf import presentation_canvas
    clock = [100.0]
    monkeypatch.setattr(presentation_canvas, 'monotonic', lambda: clock[0])
    canvas = presentation_canvas.PresentationCanvas()
    references = []
    try:
        for index in range(200):
            ghost = InkStroke([QPointF(i / 1000, .5) for i in range(1000)], 'ghost')
            ghost.created = clock[0]
            references.append(weakref.ref(ghost))
            canvas.set_ink([ghost])
            del ghost
            clock[0] += .2
            canvas.expire_ghosts()
            assert len(canvas._ghost_surfaces) <= 18
        clock[0] += 4
        canvas.expire_ghosts()
        assert all(ref() is None for ref in references)
        assert not canvas._ghost_surfaces and not canvas.ink_strokes
        assert not canvas.ghost_timer.isActive()
    finally:
        canvas.close()


def drag(canvas, start, end):
    page = canvas.page_rect()
    def position(point):
        return QPointF(page.left() + point.x() * page.width(), page.top() + point.y() * page.height()).toPoint()
    QTest.mousePress(canvas, Qt.LeftButton, pos=position(start))
    QTest.mouseMove(canvas, position(end))
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=position(end))


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_highlight_snaps_rotated_line_and_ghost_is_not_saved(tmp_path, monkeypatch, rotation):
    app = QApplication.instance() or QApplication([])
    source, target = tmp_path / 'source.pdf', tmp_path / 'highlight.pdf'
    with pdf.open() as document:
        page = document.new_page(width=400, height=300)
        page.insert_text((50, 80), 'HIGHLIGHT FIRST LINE')
        page.insert_text((50, 150), 'Do not highlight this line')
        page.set_cropbox(pdf.Rect(20, 20, 380, 280))
        page.set_rotation(rotation)
        document.save(source)
    original = source.read_bytes()
    monkeypatch.setattr(viewer_module.QFileDialog, 'getSaveFileName', lambda *a, **k: (str(target), ''))
    monkeypatch.setattr(viewer_module.QMessageBox, 'information', lambda *a: None)
    errors = []
    monkeypatch.setattr(viewer_module.QMessageBox, 'warning', lambda *a: errors.append(a))
    slides = SlideShow(source)
    slides.resize(960, 700)
    slides.show()
    app.processEvents()
    try:
        QTest.keyClick(slides, Qt.Key_H)
        assert slides.canvas.ink_tool == 'highlight'
        rect = slides.canvas.text_lines[0]
        drag(slides.canvas, rect.center(), QPointF(rect.right(), rect.center().y()))
        strokes = slides.canvas.ink_strokes
        assert len(strokes) == 1 and strokes[0].kind == 'highlight'
        assert strokes[0] == [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
        QTest.keyClick(slides, Qt.Key_P, Qt.ControlModifier)
        drag(slides.canvas, QPointF(.2, .7), QPointF(.8, .8))
        assert len(strokes) == 2 and strokes[1].kind == 'ghost'
        assert slides.bake_annotations(), errors
        assert not slides.has_ink()
        with pdf.open(target) as document:
            page = document[0]
            annotations = list(page.annots())
            assert len(annotations) == 1
            annotation = annotations[0]
            assert annotation.type[0] == pdf.PDF_ANNOT_HIGHLIGHT
            assert annotation.opacity == pytest.approx(.3)
            assert 'HIGHLIGHT FIRST LINE' in page.get_text()
            visible = [pdf.Point(point) * page.rotation_matrix for point in annotation.vertices]
            assert min(point.x for point in visible) / page.rect.width == pytest.approx(rect.left(), abs=.001)
            assert max(point.y for point in visible) / page.rect.height == pytest.approx(rect.bottom(), abs=.001)
        assert source.read_bytes() == original
    finally:
        slides.ink_by_slide.clear()
        slides.canvas.clear_ink()
        slides.close()
        app.processEvents()


def test_ghost_fades_after_three_seconds_and_stops_timer(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'source.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    slides = SlideShow(source)
    slides.resize(900, 700)
    slides.show()
    app.processEvents()
    QTest.keyClick(slides, Qt.Key_P, Qt.ControlModifier)
    drag(slides.canvas, QPointF(.2, .2), QPointF(.8, .8))
    ghost = slides.canvas.ink_strokes[0]
    assert not slides.has_ink()
    assert ghost.alpha(ghost.created + 2.9) == pytest.approx(.9)
    assert ghost.alpha(ghost.created + 3.3) == pytest.approx(.45)
    assert ghost.alpha(ghost.created + 3.7) == 0
    ghost.created = monotonic() - 3.59
    QTest.qWait(80)
    assert not slides.canvas.ink_strokes
    assert not slides.canvas.ghost_timer.isActive()
    slides.close()
    app.processEvents()
