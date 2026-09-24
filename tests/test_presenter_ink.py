import pymupdf as pdf
import pytest
import sys
from pathlib import Path
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.viewer import SlideShow
import eoingpdf.viewer as viewer_module
from eoingpdf.presentation_ink import save_presentation_ink
from eoingpdf.presentation_canvas import PresentationCanvas


def draw_stroke(canvas):
    rect = canvas.page_rect()
    positions = [QPointF(rect.left() + rect.width() * x,
                        rect.top() + rect.height() * y).toPoint()
                 for x, y in ((.2, .25), (.5, .5), (.8, .75))]
    QTest.mousePress(canvas, Qt.LeftButton, pos=positions[0])
    QTest.mouseMove(canvas, positions[1])
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=positions[2])
    return positions


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_drag_save_preserves_pages_rotation_encryption_and_source(tmp_path, monkeypatch, rotation):
    app = QApplication.instance() or QApplication([])
    source, target = tmp_path / 'original.pdf', tmp_path / 'ink.pdf'
    password = 'test-password'
    with pdf.open() as document:
        for _ in range(3):
            page = document.new_page(width=500, height=400)
            page.set_cropbox(pdf.Rect(40, 30, 440, 330))
            page.set_rotation(rotation)
        document.save(source, encryption=pdf.PDF_ENCRYPT_AES_256,
                      user_pw=password, owner_pw='test-owner')
    original = source.read_bytes()
    monkeypatch.setattr(viewer_module.QFileDialog, 'getSaveFileName', lambda *a, **k: (str(target), ''))
    monkeypatch.setattr(viewer_module.QMessageBox, 'information', lambda *a: None)
    errors = []
    monkeypatch.setattr(viewer_module.QMessageBox, 'warning', lambda *a: errors.append(a))
    window = SlideShow(source, pages=[2, 0], password=password)
    window.resize(1100, 650)
    window.show()
    app.processEvents()
    try:
        QTest.keyClick(window, Qt.Key_P)
        draw_stroke(window.canvas)
        assert window.index == 0
        first = list(window.canvas.ink_strokes[0])
        assert first[0].x() == pytest.approx(.2, abs=.003)
        assert first[0].y() == pytest.approx(.25, abs=.003)
        QTest.keyClick(window, Qt.Key_Right)
        assert not window.canvas.ink_strokes
        draw_stroke(window.canvas)
        QTest.keyClick(window, Qt.Key_Left)
        assert window.canvas.ink_strokes[0] == first
        window.resize(800, 850)
        app.processEvents()
        assert window.canvas.ink_strokes[0] == first
        assert window.bake_annotations(), errors
        assert not window.has_ink()
        with pdf.open(target) as document:
            assert document.needs_pass
            assert document.authenticate(password)
            assert document.page_count == 2
            for page in document:
                annotations = list(page.annots())
                assert len(annotations) == 1
                assert annotations[0].type[0] == pdf.PDF_ANNOT_INK
                vertices = annotations[0].vertices[0]
                for actual, expected in ((vertices[0], (.2, .25)), (vertices[-1], (.8, .75))):
                    visible = pdf.Point(actual) * page.rotation_matrix
                    assert visible.x / page.rect.width == pytest.approx(expected[0], abs=.003)
                    assert visible.y / page.rect.height == pytest.approx(expected[1], abs=.003)
        assert source.read_bytes() == original
    finally:
        window.ink_by_slide.clear()
        window.canvas.clear_ink()
        window.close()
        app.processEvents()


@pytest.mark.parametrize('ratio', [1, 1.5, 2])
def test_high_dpi_ink_ignores_page_margins(ratio):
    app = QApplication.instance() or QApplication([])
    canvas = PresentationCanvas()
    canvas.setAlignment(Qt.AlignCenter)
    canvas.resize(800, 600)
    pixmap = QPixmap(round(400 * ratio), round(300 * ratio))
    pixmap.fill(Qt.white)
    pixmap.setDevicePixelRatio(ratio)
    canvas.setPixmap(pixmap)
    canvas.show()
    canvas.toggle_ink()
    app.processEvents()
    try:
        QTest.mouseClick(canvas, Qt.LeftButton, pos=QPointF(10, 10).toPoint())
        assert not canvas.ink_strokes
        draw_stroke(canvas)
        assert canvas.ink_strokes[0][0] == QPointF(.2, .25)
        assert canvas.ink_strokes[0][-1] == QPointF(.8, .75)
        canvas.mask_suspended = True
        draw_stroke(canvas)
        assert len(canvas.ink_strokes) == 1
    finally:
        canvas.close()
        app.processEvents()


def test_publication_race_preserves_existing_file_and_cleans_temporary(tmp_path, monkeypatch):
    source, target = tmp_path / 'source.pdf', tmp_path / 'target.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    import eoingpdf.presentation_ink as ink_module
    original_link = ink_module.os.link

    def racing_link(temporary, destination):
        target.write_bytes(b'existing-user-document')
        original_link(temporary, destination)

    monkeypatch.setattr(ink_module.os, 'link', racing_link)
    with pytest.raises(FileExistsError):
        save_presentation_ink(source, target, [0], {0: [[QPointF(.1, .1), QPointF(.2, .2)]]})
    assert target.read_bytes() == b'existing-user-document'
    assert not list(tmp_path.glob('.eoing-ink-*'))


@pytest.mark.parametrize('exit_action', ['escape', 'close', 'presenter_close'])
def test_unsaved_ink_exit_cancel_and_discard(tmp_path, monkeypatch, exit_action):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'slides.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    window = SlideShow(source)
    window.resize(800, 600)
    window.show()
    app.processEvents()
    if exit_action == 'presenter_close':
        window.show_presenter()
        app.processEvents()
    QTest.keyClick(window, Qt.Key_P)
    draw_stroke(window.canvas)
    choice = ['취소']

    def respond(dialog):
        button = next(button for button in dialog.buttons() if button.text() == choice[0])
        button.click()
        return 0

    monkeypatch.setattr(viewer_module.QMessageBox, 'exec', respond)
    monkeypatch.setattr(viewer_module.QFileDialog, 'getSaveFileName', lambda *a, **k: ('', ''))

    def leave():
        if exit_action == 'escape':
            QTest.keyClick(window, Qt.Key_Escape)
        elif exit_action == 'presenter_close':
            window.presenter.close()
        else:
            window.close()
        app.processEvents()

    try:
        leave()
        assert window.isVisible()
        assert window.has_ink()
        if exit_action == 'presenter_close':
            assert window.presenter.isVisible()
            assert window.presenter.timer.isActive()
        choice[0] = '저장'
        leave()  # Cancelling the save picker must also cancel the exit.
        assert window.isVisible()
        assert window.has_ink()
        choice[0] = '저장하지 않음'
        leave()
        assert not window.isVisible()
        if exit_action == 'presenter_close':
            assert not window.presenter.isVisible()
            assert not window.presenter.timer.isActive()
    finally:
        window.ink_by_slide.clear()
        window.canvas.clear_ink()
        window.close()
        app.processEvents()


def test_mouse_ink_does_not_advance_slide(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'slides.pdf'
    with pdf.open() as document:
        document.new_page(width=400, height=300)
        document.new_page(width=400, height=300)
        document.save(source)
    window = SlideShow(source)
    window.resize(900, 700)
    window.show()
    app.processEvents()
    QTest.keyClick(window, Qt.Key_P)
    start = window.canvas.rect().center()
    end = start + QPointF(50, 30).toPoint()
    QTest.mousePress(window.canvas, Qt.LeftButton, pos=start)
    QTest.mouseMove(window.canvas, end)
    QTest.mouseRelease(window.canvas, Qt.LeftButton, pos=end)
    try:
        assert window.index == 0
        assert len(window.canvas.ink_strokes) == 1
        assert len(window.canvas.ink_strokes[0]) >= 2
    finally:
        window.canvas.clear_ink()
        window.close()
        app.processEvents()


def test_presenter_ink_can_be_baked_into_new_pdf(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'source.pdf'
    target = tmp_path / 'annotated.pdf'
    with pdf.open() as document:
        page = document.new_page(width=400, height=300)
        page.insert_text((40, 60), '판서 테스트')
        document.save(source)
    messages = []
    monkeypatch.setattr(viewer_module.QFileDialog, 'getSaveFileName',
                        lambda *args, **kwargs: (str(target), 'PDF (*.pdf)'))
    monkeypatch.setattr(viewer_module.QMessageBox, 'information',
                        lambda *args: messages.append('information'))
    monkeypatch.setattr(viewer_module.QMessageBox, 'warning',
                        lambda *args: messages.append('warning:' + str(args[2] if len(args) > 2 else args)))
    window = SlideShow(source)
    window.canvas.resize(400, 300)
    window.canvas.ink_strokes = [[QPointF(.2, .2), QPointF(.5, .5), QPointF(.8, .25)]]
    window.bake_annotations()
    assert target.is_file(), messages
    with pdf.open(target) as document:
        types = [annotation.type[0] for annotation in (document[0].annots() or ())]
        assert pdf.PDF_ANNOT_INK in types
    assert messages == ['information']
    window.close()
    app.processEvents()
