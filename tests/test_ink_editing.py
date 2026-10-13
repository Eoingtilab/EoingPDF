import sys
from pathlib import Path
import pymupdf as pdf
import pytest
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent, QPixmap, QImage, QColor
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.presentation_canvas import PresentationCanvas
from eoingpdf.ink_editing import bounds
from eoingpdf.viewer import SlideShow
from eoingpdf.presentation_ink import save_presentation_ink


def canvas():
    result = PresentationCanvas()
    result.resize(400, 300)
    result.page_size = (400, 300)
    picture = QPixmap(400, 300)
    picture.fill(Qt.white)
    result.setPixmap(picture)
    return result


def drag(widget, start, end):
    page = widget.page_rect()
    def position(point):
        return QPointF(page.x() + point.x() * page.width(), page.y() + point.y() * page.height())
    for kind, point, button, buttons in ((QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton),
                                        (QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton),
                                        (QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)):
        where = position(point)
        QApplication.sendEvent(widget, QMouseEvent(kind, where, where, button, buttons, Qt.NoModifier))


def test_partial_eraser_undo_redo_keeps_other_ink():
    surface = canvas()
    surface.set_tool('pen')
    drag(surface, QPointF(.1, .5), QPointF(.9, .5))
    surface.set_tool('erase')
    drag(surface, QPointF(.5, .5), QPointF(.5, .5))
    assert len(surface.ink_strokes) == 2
    left, right = surface.ink_strokes
    assert left[0].x() == pytest.approx(.1) and left[-1].x() < .5
    assert right[0].x() > .5 and right[-1].x() == pytest.approx(.9)
    surface.undo_ink()
    assert len(surface.ink_strokes) == 1 and len(surface.ink_strokes[0]) == 2
    surface.redo_ink()
    assert len(surface.ink_strokes) == 2
    surface.close()


@pytest.mark.parametrize('tool', ['line', 'rectangle', 'ellipse', 'arrow'])
def test_shapes_color_width_select_move_delete_and_history(tool):
    surface = canvas()
    surface.ink_color = (.8, .1, .2)
    surface.stroke_width = 7
    surface.set_tool(tool)
    drag(surface, QPointF(.1, .2), QPointF(.5, .6))
    assert len(surface.ink_strokes) == 1
    stroke = surface.ink_strokes[0]
    assert stroke.color == (.8, .1, .2) and stroke.width == 7
    previous = bounds([stroke])
    surface.set_tool('select')
    drag(surface, previous.center(), previous.center() + QPointF(.2, .1))
    moved = bounds(surface.ink_strokes)
    assert moved.x() == pytest.approx(previous.x() + .2)
    surface.delete_selected()
    assert not surface.ink_strokes
    surface.undo_ink()
    assert len(surface.ink_strokes) == 1
    surface.close()


def test_history_is_independent_per_surface_and_clear_is_undoable():
    surface = canvas()
    a, b = [], []
    surface.set_ink(a)
    surface.set_tool('pen')
    drag(surface, QPointF(.1, .1), QPointF(.2, .2))
    surface.set_ink(b)
    drag(surface, QPointF(.4, .4), QPointF(.6, .6))
    surface.undo_ink()
    assert not b and len(a) == 1
    surface.set_ink(a)
    surface.clear_ink()
    assert not a
    surface.undo_ink()
    assert len(a) == 1 and not b
    surface.close()


def test_filled_shape_has_matching_pdf_appearance(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'filled.pdf'
    with pdf.open() as document:
        document.new_page(width=400, height=300)
        document.save(source)
    surface = canvas()
    surface.shape_fill = True
    surface.ink_color = (.8, .1, .2)
    surface.set_tool('rectangle')
    drag(surface, QPointF(.1, .1), QPointF(.7, .7))
    save_presentation_ink(source, target, [0], {0: surface.ink_strokes})
    with pdf.open(target) as document:
        annotation = next(document[0].annots())
        assert annotation.colors['fill'] == pytest.approx((.8, .1, .2))
        color = document[0].get_pixmap().pixel(150, 120)
        assert color[0] > 150 and color[1] < 100
    surface.close()


@pytest.mark.parametrize('rotation', (0, 90, 180, 270))
def test_picture_move_resize_and_pdf_save_preserve_text(tmp_path, rotation):
    source, output = tmp_path / 'source.pdf', tmp_path / 'output.pdf'
    with pdf.open() as document:
        page = document.new_page(width=400, height=300)
        page.insert_text((20, 20), 'ORIGINAL TEXT')
        page.set_rotation(rotation)
        document.save(source)
    original = source.read_bytes()
    surface = canvas()
    with pdf.open(source) as document:
        surface.page_size = (document[0].rect.width, document[0].rect.height)
    image = QImage(120, 80, QImage.Format_RGBA8888)
    image.fill(QColor('#1976d2'))
    surface.add_picture(image)
    first = bounds(surface.ink_strokes)
    drag(surface, first.center(), first.center() + QPointF(.1, .05))
    moved = bounds(surface.ink_strokes)
    assert moved.x() == pytest.approx(first.x() + .1)
    drag(surface, moved.bottomRight(), moved.bottomRight() + QPointF(.08, .06))
    assert bounds(surface.ink_strokes).width() > moved.width()
    save_presentation_ink(source, output, [0], {0: surface.ink_strokes})
    with pdf.open(output) as document:
        page = document[0]
        assert page.rotation == rotation and 'ORIGINAL TEXT' in page.get_text()
        assert page.get_images()
        box = bounds(surface.ink_strokes)
        raster = page.get_pixmap()
        color = raster.pixel(round(box.center().x() * raster.width), round(box.center().y() * raster.height))
        assert color[2] > color[0] + 100
    assert source.read_bytes() == original
    surface.close()


def test_visible_toolbar_and_capture_session_stops_after_picture(tmp_path):
    source = tmp_path / 'source.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    slides = SlideShow(source)
    slides.show()
    toolbar = slides.ink_toolbar
    toolbar.buttons['erase'].click()
    assert slides.canvas.ink_tool == 'erase'
    toolbar.capture()
    assert toolbar.snipper.active and toolbar.snipper.timer.isActive()
    image = QImage(100, 60, QImage.Format_RGBA8888)
    image.fill(Qt.blue)
    # Complete before the delayed desktop-grab callback; use only synthetic pixels.
    toolbar.snipper.finish(image)
    assert not toolbar.snipper.active and not toolbar.snipper.timer.isActive()
    assert slides.canvas.ink_strokes[0].kind == 'image'
    assert slides.canvas.ink_tool == 'select'
    slides.canvas.clear_ink()
    slides.close()
