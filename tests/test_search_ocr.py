from pathlib import Path
import sys
import pytest
import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.search_text import page_blocks


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_ocr_boxes_transform_back_to_original_page(rotation, monkeypatch):
    with pdf.open() as image_document, pdf.open() as document:
        source = image_document.new_page(width=300, height=400)
        source.insert_text((40, 80), 'Account password reset', fontsize=16)
        page = document.new_page(width=300, height=400)
        page.insert_image(page.rect, stream=source.get_pixmap().tobytes('png'))
        page.set_rotation(rotation)
        expected = pdf.Rect(40, 60, 240, 85)
        visual = expected * page.rotation_matrix
        layout = dict(width=page.rect.width * 2, height=page.rect.height * 2,
            lines=[dict(text='Account password reset', words=[dict(text='Account password reset', box=[
                visual.x0 * 2, visual.y0 * 2, visual.width * 2, visual.height * 2])])])
        monkeypatch.setattr('eoingpdf.ocr.page_layout', lambda *args: layout)
        assert page_blocks(page, False) == []
        result = page_blocks(page, True)
        assert len(result) == 1 and result[0][4] == 'Account password reset'
        assert tuple(result[0][:4]) == pytest.approx(tuple(expected))
        assert not page.get_text().strip()


def test_native_text_never_invokes_ocr(monkeypatch):
    def unexpected(*args):
        pytest.fail('Native text must not invoke OCR')
    monkeypatch.setattr('eoingpdf.ocr.page_layout', unexpected)
    with pdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), 'Native text')
        assert page_blocks(page, True)[0][4].strip() == 'Native text'


@pytest.mark.parametrize('mixed', [False, True])
def test_real_windows_ocr_on_scanned_page(mixed):
    if not (ROOT / 'assets/EoingPDF.Ocr.exe').is_file():
        pytest.skip('Windows OCR bridge is not built')
    with pdf.open() as source, pdf.open() as document:
        original = source.new_page(width=400, height=200)
        original.insert_text((30, 80), 'Account password reset', fontsize=24)
        page = document.new_page(width=400, height=200)
        page.insert_image(page.rect, stream=original.get_pixmap(matrix=pdf.Matrix(2, 2)).tobytes('png'))
        if mixed:
            page.insert_text((30, 160), 'Native heading', fontsize=24)
        before = page.get_text()
        blocks = page_blocks(page, True)
        recognized = ' '.join(block[4] for block in blocks).lower()
        assert 'password' in recognized
        if mixed:
            assert recognized.count('native') == 1 and recognized.count('heading') == 1
        assert all(pdf.Rect(block[:4]).intersects(page.rect) for block in blocks)
        assert page.get_text() == before


def test_real_ocr_index_policy_refresh_and_search(tmp_path):
    from eoingpdf.semantic_search import LocalEmbedder, PdfSearchIndex
    model = ROOT / 'temp/search-model/external'
    if not (model / 'model.onnx').is_file() or not (ROOT / 'assets/EoingPDF.Ocr.exe').is_file():
        pytest.skip('Real search model and Windows OCR bridge required')
    folder = tmp_path / 'documents'; folder.mkdir()
    path = folder / 'scan.pdf'
    with pdf.open() as source, pdf.open() as document:
        original = source.new_page(width=400, height=200)
        original.insert_text((30, 80), 'Account password reset', fontsize=24)
        page = document.new_page(width=400, height=200)
        page.insert_image(page.rect, stream=original.get_pixmap(matrix=pdf.Matrix(2, 2)).tobytes('png'))
        document.save(path)
    before = path.read_bytes()
    index = PdfSearchIndex(tmp_path / 'index.db', LocalEmbedder(model))
    assert index.build(folder)['updated'] == 1
    assert index.search('password') == []
    assert index.build(folder, use_ocr=True)['updated'] == 1
    results = index.search('password reset')
    assert results and results[0]['path'] == str(path.resolve())
    assert results[0]['page'] == 0 and 'password' in results[0]['text'].lower()
    assert index.build(folder, use_ocr=True)['reused'] == 1
    assert path.read_bytes() == before
