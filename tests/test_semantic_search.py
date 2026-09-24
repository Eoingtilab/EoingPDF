import sys
from pathlib import Path
import sqlite3
import shutil
import pymupdf as pdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.semantic_search import LocalEmbedder, PdfSearchIndex, SearchCancelled


@pytest.fixture(scope='module', params=['inline', 'external'])
def embedder(request):
    pytest.importorskip('onnxruntime')
    pytest.importorskip('tokenizers')
    folder = ROOT / 'temp/search-model'
    if request.param == 'external':
        folder /= 'external'
    if not (folder / 'model.onnx').is_file():
        pytest.skip('Run scripts/prepare_search_model.py to prepare the real evaluation model')
    return LocalEmbedder(folder)


def create_pdf(path, texts, encrypted=False):
    with pdf.open() as document:
        for text in texts:
            page = document.new_page()
            page.insert_font(fontname='korean', fontfile=str(ROOT / 'assets/fonts/Pretendard-Regular.ttf'))
            page.insert_text((50, 80), text, fontname='korean', fontsize=10)
        options = dict(encryption=pdf.PDF_ENCRYPT_AES_256, user_pw='secret', owner_pw='owner') if encrypted else {}
        document.save(path, **options)


def test_real_onnx_multifile_search_returns_page_and_highlight_bounds(tmp_path, embedder):
    folder = tmp_path / 'documents'
    folder.mkdir()
    create_pdf(folder / 'manual.pdf', ['화재 발생 시 계단을 통해 건물 밖으로 대피합니다.',
        '비밀번호를 잊은 경우 로그인 화면에서 암호 재설정을 선택하고 이메일 인증을 진행합니다.'])
    create_pdf(folder / 'privacy.pdf', ['고객의 개인정보는 계약 종료 후 삼십 일 이내에 영구 삭제합니다.'])
    originals = {p: p.read_bytes() for p in folder.iterdir()}
    index = PdfSearchIndex(tmp_path / 'cache/search.db', embedder)
    assert index.build(folder)['updated'] == 2
    result = index.search('계정에 들어갈 암호가 기억나지 않습니다.', limit=1)[0]
    assert Path(result['path']).name == 'manual.pdf'
    assert result['page'] == 1
    with pdf.open(result['path']) as document:
        rect = pdf.Rect(result['rect'])
        assert not rect.is_empty and document[result['page']].rect.contains(rect)
        assert '비밀번호' in document[result['page']].get_textbox(rect)
    assert index.build(folder)['reused'] == 2
    assert all(path.read_bytes() == data for path, data in originals.items())


def test_rebuild_removes_missing_and_newly_locked_documents(tmp_path, embedder):
    folder = tmp_path / 'docs'; folder.mkdir()
    path = folder / 'file.pdf'
    create_pdf(path, ['Password reset instructions'])
    index = PdfSearchIndex(tmp_path / 'search.db', embedder)
    index.build(folder)
    path.unlink()
    create_pdf(path, ['Private locked document'], encrypted=True)
    result = index.build(folder)
    assert len(result['errors']) == 1
    assert index.search('Password') == []
    path.unlink()
    assert index.build(folder)['files'] == 0
    assert index.search('Private') == []


def test_cancel_rolls_back_model_and_document_replacement(tmp_path, embedder):
    folder = tmp_path / 'docs'; folder.mkdir()
    path = folder / 'file.pdf'
    create_pdf(path, ['Original page'])
    index = PdfSearchIndex(tmp_path / 'search.db', embedder)
    index.build(folder)
    with sqlite3.connect(index.database) as connection:
        before = connection.execute('SELECT * FROM passages').fetchall()
    path.unlink()
    create_pdf(path, ['Changed page'] * 5)
    calls = [0]
    def cancel():
        calls[0] += 1
        return calls[0] > 5
    with pytest.raises(SearchCancelled):
        index.build(folder, cancelled=cancel)
    with sqlite3.connect(index.database) as connection:
        assert connection.execute('SELECT * FROM passages').fetchall() == before
    assert index.search('Original') == []  # Old transaction survives but stale content is not served.
    assert index.build(folder)['updated'] == 1
    with pytest.raises(SearchCancelled):
        index.search('Changed', cancelled=lambda: True)


def test_corrupt_vector_is_rejected(tmp_path, embedder):
    folder = tmp_path / 'docs'; folder.mkdir()
    create_pdf(folder / 'file.pdf', ['Original page'])
    index = PdfSearchIndex(tmp_path / 'search.db', embedder)
    index.build(folder)
    with sqlite3.connect(index.database) as connection:
        connection.execute("UPDATE passages SET vector=x'1234'")
    with pytest.raises(ValueError, match='손상'):
        index.search('Original')


def test_many_stale_top_matches_do_not_hide_current_document(tmp_path, embedder):
    folder = tmp_path / 'docs'; folder.mkdir()
    stale = folder / 'old.pdf'
    valid = folder / 'current.pdf'
    create_pdf(stale, ['Password reset'] * 60)
    create_pdf(valid, ['Account recovery through email verification'])
    index = PdfSearchIndex(tmp_path / 'search.db', embedder)
    index.build(folder)
    stale.unlink()
    result = index.search('Password reset', limit=1)
    assert len(result) == 1 and result[0]['path'] == str(valid.resolve())


def test_external_model_matches_inline_and_rejects_weight_damage(tmp_path):
    pytest.importorskip('onnxruntime')
    import numpy as np
    folder = ROOT / 'temp/search-model'
    if not (folder / 'external/model.onnx').exists():
        pytest.skip('Prepare inline and external real models first')
    inline, external = LocalEmbedder(folder), LocalEmbedder(folder / 'external')
    for text in ('계정에 들어갈 암호가 기억나지 않습니다.', '文書の検索', 'Local document search'):
        np.testing.assert_array_equal(inline.encode(text), external.encode(text))
    for name in ('model.onnx', 'tokenizer.json', 'provenance.json'):
        shutil.copyfile(folder / 'external' / name, tmp_path / name)
    (tmp_path / 'weights.bin').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='가중치'):
        LocalEmbedder(tmp_path)
