import sys
from pathlib import Path
import numpy as np
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.visual_diff import compare


def document(path, rectangles, pages=1, rotation=0):
    with pdf.open() as doc:
        for _ in range(pages):
            page = doc.new_page(width=200, height=120)
            for rect in rectangles:
                page.draw_rect(pdf.Rect(rect), color=(0, 0, 0), fill=(0, 0, 0))
            page.set_rotation(rotation)
        doc.save(path)


def test_identical_has_no_difference_and_source_unchanged(tmp_path):
    path = tmp_path / 'same.pdf'
    document(path, [(20, 20, 60, 50)])
    before = path.read_bytes()
    result = compare(path, path)
    assert result.changed_pixels == 0
    assert np.array_equal(result.before, result.after)
    assert path.read_bytes() == before


def test_added_and_removed_color_masks(tmp_path):
    old, new = tmp_path / 'old.pdf', tmp_path / 'new.pdf'
    document(old, [(20, 20, 60, 50)])
    document(new, [(100, 20, 140, 50)])
    result = compare(old, new)
    assert result.changed_pixels > 0
    assert tuple(result.highlighted[60, 60]) == (215, 50, 65)
    assert tuple(result.highlighted[60, 220]) == (20, 150, 95)


def test_page_count_and_rotation_are_explicit(tmp_path):
    old, new = tmp_path / 'old.pdf', tmp_path / 'new.pdf'
    document(old, [], pages=1)
    document(new, [(20, 20, 60, 50)], pages=2, rotation=90)
    result = compare(old, new, 1, max_side=300)
    assert result.missing_before and not result.missing_after
    assert max(result.before.shape[:2]) <= 300
    assert result.changed_pixels > 0
    with pytest.raises(ValueError):
        compare(old, new, 2)


def test_authenticated_comparison(tmp_path):
    source, locked = tmp_path / 'source.pdf', tmp_path / 'locked.pdf'
    document(source, [(20, 20, 60, 50)])
    with pdf.open(source) as doc:
        doc.save(locked, encryption=pdf.PDF_ENCRYPT_AES_256, user_pw='reader', owner_pw='owner')
    with pytest.raises(ValueError):
        compare(source, locked)
    result = compare(source, locked, after_password='reader')
    assert result.changed_pixels == 0
