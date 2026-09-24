import hashlib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
from eoingpdf.advanced import transform

def test_metadata_sanitizes_zero_width_and_yellow_marks(tmp_path):
    source, target = tmp_path / 'marked.pdf', tmp_path / 'clean.pdf'
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=300)
        page.insert_text((40, 80), 'Visible text\u200b')
        page.draw_rect(pdf.Rect(100, 100, 106, 106), color=None, fill=(1, .9, .05))
        page.draw_rect(pdf.Rect(150, 150, 180, 180), color=None, fill=(1, .9, .05))
        doc.set_metadata({'author': 'secret', 'creator': 'secret'})
        doc.save(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    transform(source, target, 'metadata')
    with pdf.open(target) as doc:
        assert not doc.metadata.get('author')
        assert not doc.get_xml_metadata()
        assert 'Visible text' in doc[0].get_text()
        assert '\u200b' not in doc[0].get_text()
        assert len(doc[0].get_drawings()) == 1
        assert doc[0].get_pixmap().pixel(103, 103) == (255, 255, 255)
    assert hashlib.sha256(source.read_bytes()).digest() == before


def test_metadata_sanitize_cancel_no_publish(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'target.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((30, 30), 'text')
        doc.save(source)
    try:
        transform(source, target, 'metadata', cancelled=lambda: True)
    except Exception as error:
        assert '취소' in str(error)
    else:
        raise AssertionError('cancel should stop before publish')
    assert not target.exists()
