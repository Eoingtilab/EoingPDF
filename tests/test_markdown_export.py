import sys
from pathlib import Path
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled
from eoingpdf.markdown_export import escape, table_markdown


def test_structured_export(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'out.md'
    with pdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 60), 'Report title', fontsize=24)
        page.insert_text((40, 100), 'Body paragraph with enough words to establish normal body font.', fontsize=11)
        for y in (140, 170, 200):
            page.draw_line((40, y), (340, y))
        for x in (40, 190, 340):
            page.draw_line((x, 140), (x, 200))
        for x, y, text in [(50, 160, 'Name'), (200, 160, 'Value'), (50, 190, 'Alpha'), (200, 190, '42')]:
            page.insert_text((x, y), text, fontsize=11)
        document.new_page()
        document.save(source)
    original = source.read_bytes()
    transform(source, target, 'markdown')
    result = target.read_text(encoding='utf-8')
    assert '## Report title' in result
    assert '| Name | Value |' in result and '| Alpha | 42 |' in result
    assert result.count('Alpha') == 1
    assert '원본 페이지: 2' in result and '추출 가능한 텍스트가 없습니다' in result
    assert source.read_bytes() == original


def test_escape_table_and_markup():
    result = table_markdown([['a|b', '<script>'], ['한글\n둘째', None]])
    assert r'a\|b' in result and '&lt;script&gt;' in result
    assert '한글<br>둘째' in result
    assert '<script>' not in escape('<script>')


def test_cancel_and_existing_output(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'out.md'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    with pytest.raises(Cancelled):
        transform(source, target, 'markdown', cancelled=lambda: True)
    assert not target.exists() and not list(tmp_path.glob('.eoing-*'))
    target.write_text('existing', encoding='utf-8')
    with pytest.raises(ValueError):
        transform(source, target, 'markdown')
    assert target.read_text() == 'existing'


def test_korean_and_password(tmp_path):
    source, target = tmp_path / '한글.pdf', tmp_path / '한글.md'
    font = Path(__file__).resolve().parents[1] / 'assets/fonts/Pretendard-Regular.ttf'
    with pdf.open() as document:
        page = document.new_page()
        page.insert_font(fontname='pretendard', fontfile=str(font))
        page.insert_text((30, 80), '문서의 한글 본문을 추출합니다.', fontname='pretendard', fontsize=12)
        document.save(source, encryption=pdf.PDF_ENCRYPT_AES_256, user_pw='test-reader', owner_pw='test-owner')
    with pytest.raises(ValueError, match='암호'):
        transform(source, target, 'markdown', password='wrong')
    assert not target.exists()
    transform(source, target, 'markdown', password='test-reader')
    assert '문서의 한글 본문을 추출합니다' in target.read_text(encoding='utf-8')
