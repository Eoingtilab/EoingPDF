import re
import sys
from pathlib import Path
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled
from eoingpdf.recovery import fingerprint


def document_bytes():
    with pdf.open() as document:
        for index in range(3):
            page = document.new_page(width=600, height=400)
            page.insert_text((40, 90), f'Recovered page {index + 1}')
            page.draw_rect(pdf.Rect(20, 120, 200, 220), color=(1, 0, 0))
        document.set_toc([[1, 'Chapter', 1]])
        return document.tobytes()


@pytest.mark.parametrize('damage', ['offset', 'xref', 'tail'])
def test_rebuild_corrupted_cross_references(tmp_path, damage):
    data = document_bytes()
    if damage == 'offset':
        data = re.sub(rb'startxref\s+\d+', b'startxref\n999999999', data)
    elif damage == 'xref':
        start = data.index(b'\nxref\n')
        end = data.index(b'trailer', start)
        data = data[:start] + b'\n' + data[end:]
    else:
        data = data[:data.index(b'\nxref\n')]
    source, target = tmp_path / 'broken.pdf', tmp_path / 'restored.pdf'
    source.write_bytes(data)
    with pdf.open(source) as document:
        assert document.is_repaired
        expected = [fingerprint(page) for page in document]
    transform(source, target, 'repair')
    with pdf.open(target) as document:
        assert not document.is_repaired
        assert [fingerprint(page) for page in document] == expected
        assert document.get_toc() == [[1, 'Chapter', 1]]
    assert source.read_bytes() == data
    assert not list(tmp_path.glob('.eoing-*'))


def test_unrecoverable_input_and_existing_output(tmp_path):
    source, target = tmp_path / 'broken.pdf', tmp_path / 'out.pdf'
    source.write_bytes(b'%PDF-1.7\ninvalid binary\x00\xff')
    with pytest.raises(Exception):
        transform(source, target, 'repair')
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))
    target.write_bytes(b'keep existing output')
    with pytest.raises(ValueError, match='덮어쓸'):
        transform(source, target, 'repair')
    assert target.read_bytes() == b'keep existing output'


def test_cancel_during_verification(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'out.pdf'
    source.write_bytes(document_bytes())
    state = {'cancel': False}
    def progress(value):
        if value > 45:
            state['cancel'] = True
    with pytest.raises(Cancelled):
        transform(source, target, 'repair', progress=progress, cancelled=lambda: state['cancel'])
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))


def test_encrypted_input_requires_password(tmp_path):
    source, target = tmp_path / 'locked.pdf', tmp_path / 'out.pdf'
    with pdf.open(stream=document_bytes(), filetype='pdf') as document:
        document.save(source, encryption=pdf.PDF_ENCRYPT_AES_256,
                      user_pw='test-reader', owner_pw='test-owner')
    original = source.read_bytes()
    with pytest.raises(ValueError, match='암호'):
        transform(source, target, 'repair', password='wrong')
    assert not target.exists()
    transform(source, target, 'repair', password='test-reader')
    with pdf.open(target) as document:
        assert not document.needs_pass and not document.is_repaired
        assert len(document) == 3
    assert source.read_bytes() == original
