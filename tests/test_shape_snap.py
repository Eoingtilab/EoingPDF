import math
from pathlib import Path
import random
import sys

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pymupdf as pdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.shape_snap import snap_shape
from eoingpdf.viewer import SlideShow
import eoingpdf.viewer as viewer_module


def noisy_path(vertices, width=500, height=300, noise=.5):
    rng = random.Random(41)
    result = []
    for a, b in zip(vertices, vertices[1:]):
        for index in range(16):
            t = index / 16
            result.append(QPointF((a[0] + (b[0] - a[0]) * t + rng.uniform(-noise, noise)) / width,
                                  (a[1] + (b[1] - a[1]) * t + rng.uniform(-noise, noise)) / height))
    result.append(QPointF(vertices[-1][0] / width, vertices[-1][1] / height))
    return result


def fixtures():
    circle = [(220 + 60 * math.cos(i * 2 * math.pi / 32), 150 + 60 * math.sin(i * 2 * math.pi / 32)) for i in range(33)]
    rectangle = [(100, 70), (340, 70), (340, 220), (100, 220), (100, 70)]
    arrow = [(80, 150), (370, 150), (310, 100), (370, 150), (310, 200)]
    check = [(110, 140), (170, 200), (300, 80)]
    star = [(230 + (85 if i % 2 == 0 else 33) * math.cos(-math.pi / 2 + i * math.pi / 5),
             150 + (85 if i % 2 == 0 else 33) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
    star.append(star[0])
    return {'circle': circle, 'rectangle': rectangle, 'arrow': arrow, 'check': check, 'star': star}


@pytest.mark.parametrize('name', ['circle', 'rectangle', 'arrow', 'check', 'star'])
@pytest.mark.parametrize('reverse', [False, True])
def test_noisy_hand_drawn_shapes(name, reverse):
    points = noisy_path(fixtures()[name])
    if reverse:
        points.reverse()
    result = snap_shape(points, 500, 300)
    assert result is not None
    assert result[0] == name
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in result[1])


@pytest.mark.parametrize('vertices', [
    [(40, 60), (90, 190), (150, 80), (210, 170), (270, 40), (330, 190)],
    [(80, 100), (350, 100)],
    [(100, 100), (102, 102), (100, 104), (98, 102), (100, 100)],
    [(90, 90), (320, 90), (320, 200)],
])
def test_uncertain_writing_is_left_unchanged(vertices):
    points = noisy_path(vertices, noise=.1)
    original = list(points)
    assert snap_shape(points, 500, 300) is None
    assert points == original


@pytest.mark.parametrize('name', ['rectangle', 'arrow', 'star'])
@pytest.mark.parametrize('degrees', [25, -35])
def test_rotated_shapes(name, degrees):
    angle = math.radians(degrees)
    ca, sa = math.cos(angle), math.sin(angle)
    vertices = [(250 + .7 * ((x - 230) * ca - (y - 150) * sa),
                 150 + .7 * ((x - 230) * sa + (y - 150) * ca)) for x, y in fixtures()[name]]
    result = snap_shape(noisy_path(vertices), 500, 300)
    assert result is not None and result[0] == name


def test_crossed_star_and_invalid_input():
    star = [(240 + 70 * math.cos(-math.pi / 2 + i * 4 * math.pi / 5),
             150 + 70 * math.sin(-math.pi / 2 + i * 4 * math.pi / 5)) for i in range(6)]
    assert snap_shape(noisy_path(star), 500, 300)[0] == 'star'
    assert snap_shape([QPointF(float('nan'), 0)] * 20, 500, 300) is None
    assert snap_shape([QPointF(.2, .2)] * 20, 500, 300) is None
    assert snap_shape(noisy_path(fixtures()['circle']), 0, 300) is None


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_shape_mode_mouse_input_and_pdf_vector_save(tmp_path, monkeypatch, rotation):
    app = QApplication.instance() or QApplication([])
    source, target = tmp_path / 'source.pdf', tmp_path / 'shape.pdf'
    with pdf.open() as document:
        document.new_page(width=500, height=300).set_rotation(rotation)
        document.new_page()
        document.save(source)
    monkeypatch.setattr(viewer_module.QFileDialog, 'getSaveFileName', lambda *a, **k: (str(target), ''))
    monkeypatch.setattr(viewer_module.QMessageBox, 'information', lambda *a: None)
    errors = []
    monkeypatch.setattr(viewer_module.QMessageBox, 'warning', lambda *a: errors.append(a))
    slides = SlideShow(source)
    slides.resize(1000, 750)
    slides.show()
    app.processEvents()
    try:
        QTest.keyClick(slides, Qt.Key_D, Qt.ControlModifier)
        assert slides.canvas.ink_tool == 'shape'
        rect = slides.canvas.page_rect()
        def local(point):
            return QPointF(rect.left() + point.x() * rect.width(), rect.top() + point.y() * rect.height()).toPoint()
        points = noisy_path(fixtures()['circle'], *slides.canvas.page_size)[::5]
        QTest.mousePress(slides.canvas, Qt.LeftButton, pos=local(points[0]))
        for point in points[1:]:
            QTest.mouseMove(slides.canvas, local(point))
        QTest.mouseRelease(slides.canvas, Qt.LeftButton, pos=local(points[0]))
        assert slides.index == 0
        assert slides.canvas.ink_strokes[0].shape == 'circle'
        assert slides.bake_annotations(), errors
        with pdf.open(target) as document:
            page = document[0]
            annotation = next(page.annots())
            assert annotation.type[0] == pdf.PDF_ANNOT_INK
            vertices = annotation.vertices[0]
            assert len(vertices) == 73
            x_size = max(p[0] for p in vertices) - min(p[0] for p in vertices)
            y_size = max(p[1] for p in vertices) - min(p[1] for p in vertices)
            assert x_size == pytest.approx(y_size, abs=.05)
    finally:
        slides.ink_by_slide.clear()
        slides.canvas.clear_ink()
        slides.close()
        app.processEvents()
