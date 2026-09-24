import sys
from pathlib import Path

import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.convert import text_pdf
from eoingpdf.localization import configure_language, current_locale


@pytest.mark.parametrize('locale,heading', [('ko-KR', '문서 목차'), ('en-US', 'Document contents'), ('ja-JP', '文書の目次')])
def test_translated_cover_and_japanese_bookmark_have_readable_embedded_glyphs(tmp_path, locale, heading):
    source, target = tmp_path / 'source.pdf', tmp_path / 'cover.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((40, 70), 'Original content')
        doc.set_toc([[1, '日本語の契約書', 1]])
        doc.save(source)
    original, previous = source.read_bytes(), current_locale()
    try:
        configure_language(locale)
        transform(source, target, 'bates', bates_cover=True, bates_prefix='契約-')
    finally:
        configure_language(previous)
    with pdf.open(target) as doc:
        text = ' '.join(doc[0].get_text().split())
        assert heading in text and '日本語の契約書' in text
        assert '\x00' not in text and '\ufffd' not in text
        assert '契約-000001' in doc[1].get_text()
        assert doc[0].get_links()[0]['page'] == 1
        assert doc.get_toc() == [[1, '日本語の契約書', 2]]
        pixmap = doc[0].get_pixmap(clip=pdf.Rect(35, 30, 360, 70))
        assert min(pixmap.samples) < 100
    assert source.read_bytes() == original


def test_japanese_text_conversion_and_watermark_round_trip(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'watermarked.pdf'
    content = '日本語の文書\n한국어 문서\nEnglish document'
    text_pdf(content, source)
    original = source.read_bytes()
    transform(source, target, 'watermark_text', watermark_text='社外秘の複写')
    with pdf.open(target) as doc:
        text = ' '.join(doc[0].get_text().split())
        assert '社外秘の複写' in text
        for line in content.splitlines():
            assert line in text
        assert '\x00' not in text and '\ufffd' not in text
    assert source.read_bytes() == original
