"""Revert real PDF effects and page/stamp drafts before saving a new file."""
import io
import sys
import tempfile
from pathlib import Path

import pymupdf as pdf
from PIL import Image, ImageDraw
from pypdf import PdfReader
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import open_pdf
from eoingpdf.viewer import PdfViewer
from eoingpdf.stamp_editor import StampEditor, UNIT


def sample(path, encrypted=False):
    with pdf.open() as document:
        for index in range(3):
            page = document.new_page(width=400, height=500)
            page.insert_text((30, 120), f'PAGE {index + 1}')
            widget = pdf.Widget()
            widget.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            widget.field_name = f'field{index}'
            widget.field_value = f'VALUE {index}'
            widget.rect = pdf.Rect(30, 150, 200, 175)
            page.add_widget(widget)
        options = dict(encryption=pdf.PDF_ENCRYPT_AES_256, user_pw='secret', owner_pw='owner') if encrypted else {}
        document.save(path, **options)


def seal(path):
    image = Image.new('RGB', (70, 70), 'white')
    ImageDraw.Draw(image).ellipse((6, 6, 64, 64), outline='red', width=5)
    image.save(path)


def preview(viewer, folder, text):
    owner = tempfile.TemporaryDirectory(prefix='test-draft-', dir=folder)
    target = Path(owner.name) / 'watermark.pdf'
    source = viewer.stage_current_preview(display=False)
    transform(source, target, 'watermark_text', password=viewer.password, watermark_text=text)
    viewer.apply_preview(target, '', owner, label='문구 워터마크')
    return target, Path(owner.name)


def texts(viewer):
    with open_pdf(viewer.path, viewer.password) as document:
        return [' '.join(document[index].get_text().split()) for index in viewer.pages]


@pytest.fixture
def permissions(monkeypatch):
    monkeypatch.setattr('eoingpdf.license_ui.ensure_license', lambda *_: True)
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Discard)


def test_page_copy_contains_unsaved_stamp_and_retains_editable_draft(tmp_path, permissions, monkeypatch):
    source, image = tmp_path / 'original.pdf', tmp_path / 'seal.jpg'
    sample(source)
    original = source.read_bytes()
    seal(image)
    viewer = PdfViewer(source)
    try:
        viewer.stamp_editor = editor = StampEditor(viewer)
        editor.add_image(image)
        viewer.move_current_page(1)
        before = viewer.capture_edit_state()
        copied = []
        monkeypatch.setattr('eoingpdf.clipboard_tools.copy_page',
                            lambda page, hwnd: copied.append((page.get_text(), len(page.get_images()))))
        viewer.copy_page_image()
        assert len(copied) == 1 and 'PAGE 1' in copied[0][0] and copied[0][1] == 1
        assert viewer.capture_edit_state() == before
        assert len(editor.stamps) == 1 and viewer.undo_button.isEnabled()
        assert source.read_bytes() == original
    finally:
        viewer.close()


def test_watermarks_undo_redo_reset_without_output_or_original_changes(tmp_path, permissions):
    source = tmp_path / 'source.pdf'
    sample(source)
    original = source.read_bytes()
    viewer = PdfViewer(source)
    viewer.page.setValue(2)
    first, first_folder = preview(viewer, tmp_path, 'FIRST WATERMARK')
    second, second_folder = preview(viewer, tmp_path, 'SECOND WATERMARK')
    assert viewer.original_path == source and viewer.dirty
    assert all('FIRST WATERMARK' in value and 'SECOND WATERMARK' in value for value in texts(viewer))
    assert viewer.undo_edit() and viewer.path == first and viewer.page.value() == 2
    assert all('FIRST WATERMARK' in value and 'SECOND WATERMARK' not in value for value in texts(viewer))
    assert second.exists() and viewer.edit_history.can_redo
    assert viewer.undo_edit() and viewer.path == source and not viewer.dirty
    assert all('WATERMARK' not in value for value in texts(viewer))
    assert viewer.redo_edit() and viewer.redo_edit() and viewer.path == second
    assert viewer.reset_edits() and viewer.path == source and not viewer.dirty
    assert viewer.undo_edit() and viewer.path == second and viewer.dirty
    assert source.read_bytes() == original and len(list(tmp_path.glob('*.pdf'))) == 1
    viewer.close()
    assert not first_folder.exists() and not second_folder.exists()


def test_new_edit_after_undo_removes_unused_redo_copy(tmp_path, permissions):
    source, image = tmp_path / 'source.pdf', tmp_path / 'seal.jpg'
    sample(source)
    seal(image)
    viewer = PdfViewer(source)
    target, folder = preview(viewer, tmp_path, 'DISCARDED BRANCH')
    assert viewer.undo_edit() and target.exists()
    viewer.stamp_editor = StampEditor(viewer)
    viewer.stamp_editor.add_image(image)
    assert not viewer.edit_history.can_redo and not folder.exists()
    assert viewer.undo_edit() and not viewer.stamp_editor.stamps and not viewer.dirty
    assert viewer.redo_edit() and viewer.stamp_editor.stamps and viewer.dirty
    viewer.close()


def test_stamp_drag_is_one_step_and_undo_restores_editable_stamp(tmp_path, permissions):
    source, image = tmp_path / 'source.pdf', tmp_path / 'seal.jpg'
    sample(source)
    seal(image)
    viewer = PdfViewer(source)
    viewer.show()
    QTest.qWait(50)
    viewer.stamp_editor = editor = StampEditor(viewer)
    editor.add_image(image)
    old = editor.snapshot()[0]
    count = len(viewer.edit_history.entries)
    center = editor.overlay.screen_rect(editor.selected).center()
    for kind, point, button, buttons in [
            (QEvent.MouseButtonPress, center, Qt.LeftButton, Qt.LeftButton),
            *((QEvent.MouseMove, center + QPointF(10 * index, 5 * index), Qt.NoButton, Qt.LeftButton) for index in range(1, 5)),
            (QEvent.MouseButtonRelease, center + QPointF(40, 20), Qt.LeftButton, Qt.NoButton)]:
        QApplication.sendEvent(editor.overlay, QMouseEvent(kind, point, point, button, buttons, Qt.NoModifier))
    assert len(viewer.edit_history.entries) == count + 1 and editor.selected.x != old.x
    assert viewer.undo_edit() and editor.selected.x == old.x and editor.selected.y == old.y
    editor.width.setValue(old.width / UNIT + 3)
    assert editor.selected.width > old.width
    assert viewer.undo_edit() and editor.selected.width == old.width
    target, _ = preview(viewer, tmp_path, 'WITH SEAL')
    with pdf.open(target) as document:
        assert document[0].get_images()
    assert not editor.stamps
    assert viewer.undo_edit() and editor.stamps and viewer.path == source
    editor.remove_selected()
    assert not viewer.dirty
    viewer.close()


def test_page_delete_undo_keeps_stamp_and_canonical_fields_with_encryption(tmp_path, permissions, monkeypatch):
    source, image, output = tmp_path / 'source.pdf', tmp_path / 'seal.jpg', tmp_path / 'saved.pdf'
    sample(source, encrypted=True)
    original = source.read_bytes()
    seal(image)
    monkeypatch.setattr('eoingpdf.viewer.QInputDialog.getText', lambda *_: ('secret', True))
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Yes)
    viewer = PdfViewer(source)
    viewer.page.setValue(2)
    viewer.stamp_editor = editor = StampEditor(viewer)
    editor.add_image(image)
    viewer.stage_delete({1})
    assert viewer.pages == [0, 2] and not editor.stamps
    assert viewer.undo_edit() and viewer.pages == [0, 1, 2] and editor.selected.page == 1
    viewer.move_current_page(1)
    before = viewer.capture_edit_state()
    staged = viewer.stage_current_preview(display=False)
    assert viewer.capture_edit_state() == before and editor.stamps
    with pdf.open(staged) as document:
        assert document.needs_pass and document.authenticate('secret')
        assert [next(page.widgets()).field_name for page in document] == ['field0', 'field2', 'field1']
        assert document[2].get_images()
    viewer.stage_delete({0})
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(output), 'PDF'))
    assert viewer.save_changes() and not viewer.edit_history.can_undo and not viewer.dirty
    with pdf.open(output) as document:
        assert document.needs_pass and document.authenticate('secret')
        reader = PdfReader(io.BytesIO(document.tobytes(encryption=pdf.PDF_ENCRYPT_NONE)))
        assert {key: value['/V'] for key, value in reader.get_fields().items()} == {
            'field1': 'VALUE 1', 'field2': 'VALUE 2'}
        assert document[1].get_images()
    assert source.read_bytes() == original
    viewer.close()


def test_history_limit_releases_old_previews_and_keeps_original_reset(tmp_path, permissions):
    source = tmp_path / 'source.pdf'
    sample(source)
    viewer = PdfViewer(source)
    viewer.edit_history.limit = 3
    folders = []
    for index in range(7):
        _, folder = preview(viewer, tmp_path, f'MARK {index}')
        folders.append(folder)
    assert len(viewer.edit_history.entries) == 4
    assert all(not folder.exists() for folder in folders[:3])
    assert all(folder.exists() for folder in folders[3:])
    assert viewer.reset_edits() and viewer.path == source and not viewer.dirty
    assert all('MARK ' not in text for text in texts(viewer))
    assert viewer.undo_edit() and 'MARK 6' in texts(viewer)[0]
    viewer.close()
    assert all(not folder.exists() for folder in folders)


def test_failed_undo_keeps_current_document_and_history_cursor(tmp_path, permissions, monkeypatch):
    source = tmp_path / 'source.pdf'
    sample(source)
    viewer = PdfViewer(source)
    first, _ = preview(viewer, tmp_path, 'FIRST')
    second, _ = preview(viewer, tmp_path, 'SECOND')
    first.unlink()
    warnings = []
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.warning', lambda *args: warnings.append(args[-1]))
    before, cursor = viewer.capture_edit_state(), viewer.edit_history.position
    assert not viewer.undo_edit()
    assert viewer.capture_edit_state() == before and viewer.edit_history.position == cursor
    assert viewer.path == second and 'SECOND' in texts(viewer)[0] and warnings
    viewer.close()


def test_materialized_display_then_new_stamp_branches_without_double_stamping(tmp_path, permissions, monkeypatch):
    source, image, output = tmp_path / 'source.pdf', tmp_path / 'seal.jpg', tmp_path / 'saved.pdf'
    sample(source)
    original = source.read_bytes()
    seal(image)
    viewer = PdfViewer(source)
    viewer.stamp_editor = editor = StampEditor(viewer)
    editor.add_image(image)
    initial_count = len(viewer.edit_history.entries)
    viewer.stage_current_preview(display=True)
    assert len(viewer.edit_history.entries) == initial_count and not editor.stamps
    editor.add_image(image)
    editor.width.setValue(20)
    assert viewer.undo_edit() and viewer.undo_edit()
    assert viewer.path == source and len(editor.stamps) == 1
    assert viewer.redo_edit() and viewer.redo_edit() and len(editor.stamps) == 1
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(output), 'PDF'))
    assert viewer.save_changes()
    with pdf.open(output) as document:
        assert len(document[0].get_image_info()) == 2
        assert PdfReader(output).get_fields()['field0']['/V'] == 'VALUE 0'
    assert source.read_bytes() == original
    viewer.close()


def test_same_image_reuses_pixmap_across_deleted_stamps_and_history(tmp_path, permissions):
    source, image = tmp_path / 'source.pdf', tmp_path / 'seal.jpg'
    sample(source)
    seal(image)
    viewer = PdfViewer(source)
    viewer.stamp_editor = editor = StampEditor(viewer)
    editor.add_image(image)
    first = editor.selected.pixmap
    retained_bytes = viewer.edit_history.image_bytes()
    editor.remove_selected()
    assert not editor.image_cache and not editor.stamps and not viewer.dirty
    editor.add_image(image)
    assert editor.selected.pixmap is first
    assert viewer.edit_history.image_bytes() == retained_bytes
    viewer.close()
    assert viewer.edit_history is None and not editor.stamps and not editor.image_cache


def test_filled_form_undo_redo_restores_canonical_values(tmp_path, permissions, monkeypatch):
    source, output = tmp_path / 'source.pdf', tmp_path / 'saved.pdf'
    sample(source)
    original = source.read_bytes()
    viewer = PdfViewer(source)
    with pdf.open(source) as document:
        key = str(next(document[0].widgets()).xref)
    owner = tempfile.TemporaryDirectory(prefix='test-fields-', dir=tmp_path)
    target = Path(owner.name) / 'filled.pdf'
    transform(source, target, 'fill_forms', form_values={key: '홍길동'})
    viewer.apply_preview(target, '', owner, label='양식 입력')
    assert PdfReader(viewer.path).get_fields()['field0']['/V'] == '홍길동'
    assert viewer.undo_edit() and PdfReader(viewer.path).get_fields()['field0']['/V'] == 'VALUE 0'
    assert viewer.redo_edit() and PdfReader(viewer.path).get_fields()['field0']['/V'] == '홍길동'
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(output), 'PDF'))
    assert viewer.save_changes()
    assert PdfReader(output).get_fields()['field0']['/V'] == '홍길동'
    assert source.read_bytes() == original
    viewer.close()


def test_failed_save_open_and_cancel_close_preserve_preview_history(tmp_path, permissions, monkeypatch):
    source = tmp_path / 'source.pdf'
    sample(source)
    original = source.read_bytes()
    viewer = PdfViewer(source)
    target, folder = preview(viewer, tmp_path, 'CURRENT DRAFT')
    before, cursor = viewer.capture_edit_state(), viewer.edit_history.position
    warnings = []
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.warning', lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr('eoingpdf.viewer.QFileDialog.getSaveFileName', lambda *_: (str(target), 'PDF'))
    assert not viewer.save_changes() and warnings
    with pytest.raises(ValueError, match='사본'):
        viewer.load(target)
    with pytest.raises(Exception):
        viewer.load(tmp_path / 'missing.pdf')
    assert viewer.capture_edit_state() == before and viewer.edit_history.position == cursor and viewer.dirty
    viewer.show()
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Cancel)
    viewer.close()
    assert viewer.isVisible() and folder.exists() and viewer.edit_history.position == cursor
    assert 'CURRENT DRAFT' in texts(viewer)[0] and source.read_bytes() == original
    monkeypatch.setattr('eoingpdf.viewer.QMessageBox.question', lambda *_: QMessageBox.Discard)
    viewer.close()
    assert not folder.exists() and viewer.edit_history is None
