import sys
from pathlib import Path
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Request, run


def test_merged_document_bookmarks_and_clickable_cover(tmp_path):
    paths = []
    for index in range(2):
        path = tmp_path / f'Document{index + 1}.pdf'
        with pdf.open() as document:
            page = document.new_page()
            page.insert_text((40, 80), f'Original {index + 1}')
            document.save(path)
        paths.append(str(path))
    merged = run(Request('merge', tuple(paths), str(tmp_path)))
    # Core operations return a path to the generated file.
    merged = Path(merged)
    before = merged.read_bytes()
    target = tmp_path / 'bates.pdf'
    transform(merged, target, 'bates', bates_prefix='DOC-', bates_start=20, bates_digits=4, bates_cover=True)
    with pdf.open(target) as document:
        assert len(document) == 3
        assert [link['page'] for link in document[0].get_links()] == [1, 2]
        assert 'DOC-0020' in document[1].get_text() and 'DOC-0021' in document[2].get_text()
        assert document.get_toc() == [[1, 'Document1', 2], [1, 'Document2', 3]]
    assert merged.read_bytes() == before


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_number_at_displayed_bottom(tmp_path, rotation):
    source, target = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.set_cropbox(pdf.Rect(50, 70, 550, 730))
        page.set_rotation(rotation)
        document.save(source)
    transform(source, target, 'bates', bates_prefix='TEST-')
    with pdf.open(target) as document:
        page = document[0]
        box = page.search_for('TEST-000001')[0] * page.rotation_matrix
        assert page.rect.contains(box)
        assert box.y0 > page.rect.height - 35
        assert abs((box.x0 + box.x1) / 2 - page.rect.width / 2) < 1


def test_old_number_is_physically_redacted(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((30, 770), '77', fontsize=12)
        page.insert_text((30, 730), 'Keep footer text', fontsize=12)
        document.save(source)
    transform(source, target, 'bates')
    with pdf.open(target) as document:
        page = document[0]
        assert '77' not in page.get_text() and 'Keep footer text' in page.get_text()
        assert not page.search_for('77')


def test_invalid_prefix_does_not_publish(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    with pytest.raises(ValueError):
        transform(source, target, 'bates', bates_prefix='Bad\nPrefix')
    assert not target.exists() and not list(tmp_path.glob('.eoing-*'))
