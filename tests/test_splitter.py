import sys
import zipfile
from pathlib import Path
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled


@pytest.fixture
def source(tmp_path):
    source = tmp_path / 'source.pdf'
    with pdf.open() as doc:
        for index in range(7):
            doc.new_page().insert_text((30, 40), f'PAGE {index + 1}')
        doc.set_toc([[1, '../../chapter', 3], [2, 'Nested', 4], [1, 'Last', 6]])
        doc.save(source)
    return source


def contents(path):
    with zipfile.ZipFile(path) as archive:
        result = []
        for name in archive.namelist():
            assert '/' not in name and '\\' not in name
            with pdf.open(stream=archive.read(name), filetype='pdf') as doc:
                result.append([page.get_text().strip() for page in doc])
        return result


def test_ranges_end_and_reverse(source, tmp_path):
    target = tmp_path / 'ranges.zip'
    transform(source, target, 'split_ranges', split_ranges='1-3, 5, 7-6')
    assert contents(target) == [['PAGE 1', 'PAGE 2', 'PAGE 3'], ['PAGE 5'], ['PAGE 7', 'PAGE 6']]
    other = tmp_path / 'end.zip'
    transform(source, other, 'split_ranges', split_ranges='5-end')
    assert contents(other) == [['PAGE 5', 'PAGE 6', 'PAGE 7']]


def test_groups_preserve_short_tail(source, tmp_path):
    target = tmp_path / 'groups.zip'
    transform(source, target, 'split_groups', group_size=3)
    assert [len(group) for group in contents(target)] == [3, 3, 1]


def test_toc_preserves_front_matter_and_all_pages(source, tmp_path):
    before = source.read_bytes()
    target = tmp_path / 'toc.zip'
    transform(source, target, 'split_toc')
    result = contents(target)
    assert [len(group) for group in result] == [2, 3, 2]
    assert sum(result, []) == [f'PAGE {index + 1}' for index in range(7)]
    assert source.read_bytes() == before


@pytest.mark.parametrize('ranges', ['', '1,,2', '0-2', '8-end'])
def test_invalid_plan_leaves_no_output(source, tmp_path, ranges):
    target = tmp_path / 'invalid.zip'
    with pytest.raises(ValueError):
        transform(source, target, 'split_ranges', split_ranges=ranges)
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))


def test_cancel_does_not_publish(source, tmp_path):
    target = tmp_path / 'cancel.zip'
    with pytest.raises(Cancelled):
        transform(source, target, 'split_groups', cancelled=lambda: True)
    assert not target.exists()
