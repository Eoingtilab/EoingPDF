"""Exercise daily office workflows using generated, mixed-layout PDFs."""
import sys
from pathlib import Path
from time import monotonic

import pymupdf as pdf
import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QLineEdit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced_ui import AdvancedDialog
from eoingpdf.core import open_pdf
from eoingpdf.form_ui import FormDialog
from eoingpdf.ink_stroke import InkStroke
from eoingpdf.stamp_editor import StampEditor
from eoingpdf.viewer import PdfViewer, SlideShow


def office_pdf(path, count=50, password=''):
    """Keep text, crop, rotation, navigation and interactive fields together."""
    with pdf.open() as document:
        for index in range(count):
            page = document.new_page(width=420, height=560)
            page.insert_text((60, 110), f'OFFICE PAGE {index + 1:02}')
            page.draw_rect(pdf.Rect(55, 165, 310, 195), color=(.4, .4, .4))
            field = pdf.Widget()
            field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            field.field_name = f'office_{index + 1:02}'
            field.field_value = f'ORIGINAL {index + 1:02}'
            field.rect = pdf.Rect(60, 168, 300, 190)
            page.add_widget(field)
            page.insert_link({'kind': pdf.LINK_URI, 'from': pdf.Rect(60, 125, 260, 140),
                              'uri': f'https://example.invalid/office/{index + 1}'})
            page.set_cropbox(pdf.Rect(20, 20, 400, 540))
            page.set_rotation((index % 4) * 90)
        document[0].insert_link({'kind': pdf.LINK_GOTO, 'from': pdf.Rect(70, 200, 250, 220),
                                 'page': count - 1, 'to': pdf.Point(60, 90)})
        document.set_metadata({'title': 'Generated office workflow fixture'})
        document.set_toc([[1, 'Beginning', 1], [1, 'Last page', count]])
        options = dict(encryption=pdf.PDF_ENCRYPT_AES_256, user_pw=password,
                       owner_pw='generated-owner') if password else {}
        document.save(path, **options)


def seal_jpg(path):
    image = Image.new('RGB', (100, 100), 'white')
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 92, 92), outline=(220, 0, 0), width=7)
    image.save(path, quality=95)


def wait_for_worker(dialog, timeout=15):
    deadline = monotonic() + timeout
    while not dialog.worker.done and monotonic() < deadline:
        QTest.qWait(10)
    assert dialog.worker.done, dialog.status.text()
    QTest.qWait(10)


@pytest.fixture
def permissions(monkeypatch):
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Yes)
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.information', lambda *_: None)
    warnings = []
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.warning', lambda *args: warnings.append(args[-1]))
    return warnings


def close_cleanly(viewer, monkeypatch):
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Discard)
    viewer.close()


@pytest.mark.parametrize('current,deleted,expected', [
    (4, {1}, 4),          # A preceding page was removed; keep the current content.
    (4, {3}, 5),          # The current page was removed; move to the next survivor.
    (8, {6, 7}, 6),       # The tail was removed; use the last surviving page.
])
def test_delete_and_history_keep_current_page_content(tmp_path, permissions, monkeypatch, current, deleted, expected):
    source = tmp_path / 'source.pdf'
    office_pdf(source, 8)
    viewer = PdfViewer(source)
    try:
        viewer.page.setValue(current)
        viewer.stage_delete(deleted)
        assert viewer.pages[viewer.page.value() - 1] + 1 == expected
        assert viewer.undo_edit()
        assert viewer.pages[viewer.page.value() - 1] + 1 == current
        assert viewer.redo_edit()
        assert viewer.pages[viewer.page.value() - 1] + 1 == expected
    finally:
        close_cleanly(viewer, monkeypatch)


@pytest.mark.parametrize('delta', [-1, 1])
def test_move_and_history_follow_the_selected_page(tmp_path, permissions, monkeypatch, delta):
    source = tmp_path / 'source.pdf'
    office_pdf(source, 8)
    viewer = PdfViewer(source)
    try:
        viewer.page.setValue(4)
        viewer.move_current_page(delta)
        assert viewer.page.value() == 4 + delta
        assert viewer.pages[viewer.page.value() - 1] == 3
        assert viewer.undo_edit() and viewer.page.value() == 4
        assert viewer.pages[viewer.page.value() - 1] == 3
        assert viewer.redo_edit() and viewer.page.value() == 4 + delta
        assert viewer.pages[viewer.page.value() - 1] == 3
    finally:
        close_cleanly(viewer, monkeypatch)


def test_enter_in_page_number_goes_to_that_page_without_extra_navigation(tmp_path, permissions, monkeypatch):
    source = tmp_path / 'source.pdf'
    office_pdf(source, 8)
    viewer = PdfViewer(source)
    try:
        viewer.show()
        viewer.page.setFocus()
        viewer.page.selectAll()
        QTest.keyClicks(viewer.page, '7')
        QTest.keyClick(viewer.page, Qt.Key_Return)
        assert viewer.page.value() == 7
        assert viewer.pages[viewer.page.value() - 1] == 6 and viewer.isVisible()
        assert not viewer.dirty and not viewer.edit_history.can_undo
    finally:
        close_cleanly(viewer, monkeypatch)


@pytest.mark.parametrize('count,current', [(8, 4), (50, 23)])
def test_stamp_watermark_form_page_changes_undo_save_keep_office_data(tmp_path, permissions, monkeypatch, count, current):
    source, seal, output = tmp_path / 'source.pdf', tmp_path / 'seal.jpg', tmp_path / 'saved.pdf'
    office_pdf(source, count)
    seal_jpg(seal)
    original = source.read_bytes()
    viewer = PdfViewer(source)
    try:
        viewer.page.setValue(current)
        viewer.stamp_editor = editor = StampEditor(viewer)
        editor.add_image(seal)
        stamp_state = viewer.capture_edit_state()

        watermark = AdvancedDialog(viewer)
        watermark.source.setText(str(viewer.stage_current_preview(display=False)))
        watermark.tool.setCurrentIndex(watermark.tool.findData('watermark_text'))
        watermark.watermark_text.setText('OFFICE REVIEW')
        watermark.start(preview=True)
        wait_for_worker(watermark)
        assert viewer.path != source and viewer.page.value() == current
        assert viewer.undo_edit() and viewer.capture_edit_state() == stamp_state
        assert editor.stamps and viewer.redo_edit() and not editor.stamps

        form = FormDialog(viewer.path, current - 1, viewer, password=viewer.password)
        assert len(form.fields) == 1
        field = next(iter(form.fields.values()))
        assert isinstance(field, QLineEdit)
        field.setText('검토 완료 2026')
        form.start()
        wait_for_worker(form)
        assert PdfReader(viewer.path).get_fields()[f'office_{current:02}']['/V'] == '검토 완료 2026'
        assert viewer.undo_edit()
        assert PdfReader(viewer.path).get_fields()[f'office_{current:02}']['/V'] == f'ORIGINAL {current:02}'
        assert viewer.redo_edit()

        viewer.move_current_page(1)
        reordered = viewer.pages[:]
        viewer.stage_delete({2})
        assert viewer.undo_edit() and viewer.pages == reordered
        assert viewer.redo_edit()
        expected = [page + 1 for page in viewer.pages]
        before_save = viewer.capture_edit_state()
        monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: ('', ''))
        assert not viewer.save_changes() and viewer.capture_edit_state() == before_save
        monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(output), 'PDF'))
        assert viewer.save_changes()
        reader = PdfReader(output)
        assert set(reader.get_fields()) == {f'office_{number:02}' for number in expected}
        assert reader.get_fields()[f'office_{current:02}']['/V'] == '검토 완료 2026'
        with pdf.open(output) as document:
            assert document.page_count == count - 1
            assert document.metadata['title'] == 'Generated office workflow fixture'
            for index, number in enumerate(expected):
                page = document[index]
                assert f'OFFICE PAGE {number:02}' in page.get_text()
                assert 'OFFICE REVIEW' in ' '.join(page.get_text().split())
                assert page.rotation == ((number - 1) % 4) * 90
                assert page.cropbox == pdf.Rect(20, 20, 400, 540)
                assert any(link.get('uri') == f'https://example.invalid/office/{number}' for link in page.get_links())
            stamped = document[expected.index(current)]
            assert len(stamped.get_image_info()) == 1
            raster = stamped.get_pixmap(colorspace=pdf.csRGB)
            pixels = raster.samples
            assert sum(pixels[index] > 150 and pixels[index + 1] < 100 and pixels[index + 2] < 100
                       for index in range(0, len(pixels), 3)) > 100
            assert any(link['kind'] == pdf.LINK_GOTO and link['page'] == len(expected) - 1
                       for link in document[0].get_links())
        assert source.read_bytes() == original and not viewer.dirty
        assert not viewer.edit_history.can_undo and not viewer.edit_history.can_redo
    finally:
        close_cleanly(viewer, monkeypatch)


def test_cancel_open_password_and_failed_save_leave_the_exact_draft(tmp_path, permissions, monkeypatch):
    source, secret, seal = tmp_path / 'source.pdf', tmp_path / 'secret.pdf', tmp_path / 'seal.jpg'
    office_pdf(source, 8)
    office_pdf(secret, 2, password='generated-secret')
    seal_jpg(seal)
    original = source.read_bytes()
    viewer = PdfViewer(source)
    try:
        viewer.stamp_editor = StampEditor(viewer)
        viewer.stamp_editor.add_image(seal)
        viewer.page.setValue(4)
        viewer.move_current_page(1)
        before = viewer.capture_edit_state()
        position = viewer.edit_history.position
        monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Discard)
        monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getOpenFileName', lambda *_: ('', ''))
        viewer.choose_pdf()
        assert viewer.capture_edit_state() == before
        prompts = iter([('incorrect', True), ('', False)])
        monkeypatch.setattr('eoingpdf.viewer.QInputDialog.getText', lambda *_: next(prompts))
        monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getOpenFileName', lambda *_: (str(secret), 'PDF'))
        viewer.choose_pdf()
        assert viewer.capture_edit_state() == before and viewer.edit_history.position == position
        monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Cancel)
        viewer.show()
        assert not viewer.close() and viewer.isVisible() and viewer.capture_edit_state() == before
        monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(tmp_path / 'never.pdf'), 'PDF'))
        monkeypatch.setattr('eoingpdf.jobs.publish', lambda *_: (_ for _ in ()).throw(OSError('generated save failure')))
        assert not viewer.save_changes()
        assert viewer.capture_edit_state() == before and viewer.edit_history.position == position
        assert not (tmp_path / 'never.pdf').exists() and source.read_bytes() == original
        assert permissions
    finally:
        close_cleanly(viewer, monkeypatch)


def test_cancel_and_fail_watermark_worker_keep_seal_page_order_and_undo(tmp_path, permissions, monkeypatch):
    source, seal = tmp_path / 'source.pdf', tmp_path / 'seal.jpg'
    office_pdf(source)
    seal_jpg(seal)
    viewer = PdfViewer(source)
    try:
        viewer.stamp_editor = StampEditor(viewer)
        viewer.stamp_editor.add_image(seal)
        viewer.move_current_page(1)
        before = viewer.capture_edit_state()
        for cancel in (True, False):
            dialog = AdvancedDialog(viewer)
            dialog.source.setText(str(viewer.stage_current_preview(display=False)))
            dialog.tool.setCurrentIndex(dialog.tool.findData('watermark_text'))
            dialog.watermark_text.setText('GENERATED' if cancel else '')
            dialog.start(preview=True)
            if cancel:
                dialog.reject()
            wait_for_worker(dialog)
            assert not dialog.preview_success
            assert dialog.preview_owner is None
            assert viewer.capture_edit_state() == before
            assert viewer.undo_edit() and viewer.redo_edit()
            assert viewer.capture_edit_state() == before
            dialog.reject()
    finally:
        close_cleanly(viewer, monkeypatch)


def test_presentation_save_returns_stamp_ink_picture_board_and_forms_to_viewer(tmp_path, permissions, monkeypatch):
    source, seal, output = tmp_path / 'source.pdf', tmp_path / 'seal.jpg', tmp_path / 'presentation.pdf'
    office_pdf(source, 8)
    seal_jpg(seal)
    original = source.read_bytes()
    viewer = PdfViewer(source)
    slides = None
    try:
        viewer.page.setValue(4)
        viewer.stamp_editor = StampEditor(viewer)
        viewer.stamp_editor.add_image(seal)
        viewer.move_current_page(1)
        viewer.stage_delete({2})
        expected = [page + 1 for page in viewer.pages]
        viewer.page.setValue(expected.index(4) + 1)
        staged = viewer.stage_current_preview(display=False)
        slides = SlideShow(staged, viewer.page.value() - 1, viewer)
        slides.viewer_draft_path = staged
        slides.canvas.resize(600, 600)
        slides.render()
        selected = slides.index
        pen = InkStroke([QPointF(.1, .1), QPointF(.2, .2)], 'pen')
        pen.color = (0, 0, 1)
        slides.canvas.set_ink([pen])
        picture = QImage(40, 30, QImage.Format_RGB32)
        picture.fill(0xff00aa00)
        slides.canvas.add_picture(picture)
        slides.stash_surface()
        slides.set_blank('white')
        slides.canvas.set_ink([InkStroke([QPointF(.2, .2), QPointF(.3, .3)], 'pen')])
        monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: ('', ''))
        assert not slides.bake_annotations() and slides.has_ink()
        monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(output), 'PDF'))
        assert slides.bake_annotations() and not slides.has_ink()
        viewer.finish_slideshow(slides)
        assert viewer.path == output and viewer.count == len(expected) + 1 and not viewer.dirty
        fields = PdfReader(output).get_fields()
        assert set(fields) == {f'office_{number:02}' for number in expected}
        with open_pdf(output) as document:
            slide = document[selected]
            assert f'OFFICE PAGE {expected[selected]:02}' in slide.get_text()
            assert len(slide.get_image_info()) == 2
            assert len(list(slide.annots())) == 1
            board = document[selected + 1]
            assert len(list(board.annots())) == 1 and not list(board.widgets())
            assert [f'OFFICE PAGE {number:02}' in document[index + (index > selected)].get_text()
                    for index, number in enumerate(expected)] == [True] * len(expected)
        assert source.read_bytes() == original
    finally:
        if slides:
            slides.canvas.set_ink([])
            slides.ink_by_slide.clear()
            slides.boards.clear()
            slides.reject()
        close_cleanly(viewer, monkeypatch)


def test_cancel_closing_presentation_keeps_viewer_and_editable_drafts(tmp_path, permissions, monkeypatch):
    source, seal = tmp_path / 'source.pdf', tmp_path / 'seal.jpg'
    office_pdf(source, 8)
    seal_jpg(seal)
    viewer = PdfViewer(source)
    slides = None
    try:
        viewer.stamp_editor = StampEditor(viewer)
        viewer.stamp_editor.add_image(seal)
        viewer.show()
        viewer.start_slideshow()
        slides = viewer.slideshow
        slides.canvas.set_ink([InkStroke([QPointF(.1, .1), QPointF(.2, .2)], 'pen')])
        before = viewer.capture_edit_state()
        draft_path = slides.path
        monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question',
                            lambda *_: pytest.fail('The viewer must stay open when its presentation exit is cancelled.'))
        monkeypatch.setattr('eoingpdf.viewer.QMessageBox.exec', lambda *_: None)
        monkeypatch.setattr('eoingpdf.viewer.QMessageBox.clickedButton',
                            lambda dialog: next(button for button in dialog.buttons()
                                                if dialog.buttonRole(button) == QMessageBox.RejectRole))
        assert not viewer.close()
        assert viewer.isVisible() and slides.isVisible() and slides.has_ink()
        assert viewer.capture_edit_state() == before and draft_path.exists()
        assert viewer.stamp_editor.stamps and viewer.undo_button.isEnabled()
    finally:
        if slides:
            slides.canvas.set_ink([])
            slides.ink_by_slide.clear()
            slides.boards.clear()
            slides.reject()
        close_cleanly(viewer, monkeypatch)
