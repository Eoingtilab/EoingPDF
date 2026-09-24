import sys
from pathlib import Path

import pymupdf as pdf
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.ink_stroke import InkStroke
from eoingpdf.presentation_ink import save_presentation_ink
from eoingpdf.viewer import SlideShow
import eoingpdf.viewer as viewer_module
from test_presenter_ink import draw_stroke


def stroke(kind='pen'):
    return InkStroke([QPointF(.2, .3), QPointF(.7, .6)], kind=kind)


@pytest.mark.parametrize('encrypted', [False, True])
def test_board_save_order_and_repeated_save(tmp_path, monkeypatch, encrypted):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'source.pdf'
    password = 'board-test' if encrypted else ''
    with pdf.open() as document:
        for name in ('FIRST', 'SECOND'):
            page = document.new_page(width=500, height=300)
            page.insert_text((40, 40), name)
        document.save(source, encryption=pdf.PDF_ENCRYPT_AES_256 if encrypted else pdf.PDF_ENCRYPT_NONE,
                      user_pw=password, owner_pw='owner')
    original = source.read_bytes()
    targets = iter([tmp_path / 'first.pdf', tmp_path / 'second.pdf'])
    monkeypatch.setattr(viewer_module.QFileDialog, 'getSaveFileName', lambda *a, **k: (str(next(targets)), ''))
    monkeypatch.setattr(viewer_module.QMessageBox, 'information', lambda *a: None)
    errors = []
    monkeypatch.setattr(viewer_module.QMessageBox, 'warning', lambda *a: errors.append(a))
    window = SlideShow(source, password=password)
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    try:
        window.select_ink_tool('pen')
        draw_stroke(window.canvas)
        original_ink = window.canvas.ink_strokes
        window.set_blank('black')
        assert not window.canvas.ink_strokes
        draw_stroke(window.canvas)
        black_ink = window.canvas.ink_strokes
        size = window.canvas.page_size
        window.resize(600, 800)
        app.processEvents()
        assert window.canvas.page_size == size
        window.set_blank('white')
        draw_stroke(window.canvas)
        window.set_blank('white')
        assert window.canvas.ink_strokes is original_ink
        window.set_blank('black')
        assert window.canvas.ink_strokes is black_ink
        window.advance(1)
        assert not window.canvas.ink_strokes
        window.advance(-1)
        assert window.canvas.ink_strokes is original_ink
        window.set_blank('black')
        assert window.bake_annotations(), errors
        assert window.count == 4
        assert window.index == 1
        assert window.viewer_indices == [0, 0, 0, 1]
        assert not window.has_ink()
        assert not window.blank
        with pdf.open(window.path) as document:
            if encrypted:
                assert document.needs_pass
                assert document.authenticate(password)
            assert 'FIRST' in document[0].get_text()
            assert 'SECOND' in document[3].get_text()
            for index in (0, 1, 2):
                assert len(list(document[index].annots())) == 1
            for index, expected in ((1, (0, 0, 0)), (2, (255, 255, 255))):
                image = document[index].get_pixmap()
                assert image.pixel(5, 5) == expected
        window.select_ink_tool('pen')
        draw_stroke(window.canvas)
        assert window.bake_annotations(), errors
        assert window.count == 4
        assert window.viewer_indices == [0, 0, 0, 1]
        with pdf.open(window.path) as document:
            if encrypted:
                document.authenticate(password)
            assert len(list(document[1].annots())) == 2
        assert source.read_bytes() == original
    finally:
        window.boards.clear()
        window.ink_by_slide.clear()
        window.canvas.set_ink([])
        window.close()
        app.processEvents()


def test_empty_and_ghost_boards_not_saved_and_invalid_board_is_atomic(tmp_path):
    source = tmp_path / 'source.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    boards = {(0, 'black'): {'size': (720, 400), 'strokes': [stroke('ghost')]},
              (0, 'white'): {'size': (720, 400), 'strokes': []}}
    target = tmp_path / 'empty.pdf'
    save_presentation_ink(source, target, [0], {}, boards=boards)
    with pdf.open(target) as document:
        assert len(document) == 1
    boards[(0, 'black')] = {'size': (float('nan'), 400), 'strokes': [stroke()]}
    target = tmp_path / 'invalid.pdf'
    with pytest.raises(ValueError):
        save_presentation_ink(source, target, [0], {}, boards=boards)
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-ink-*'))
