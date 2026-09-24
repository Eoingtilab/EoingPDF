from pathlib import Path
import sys
import json

import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.convert import to_pdf
from eoingpdf.core import Cancelled


@pytest.mark.parametrize('outcome', ['error', 'cancel', 'collision', 'success'])
def test_conversion_publishes_only_complete_new_outputs(tmp_path, monkeypatch, outcome):
    source, target = tmp_path / 'source.docx', tmp_path / 'result.pdf'
    source.write_bytes(b'original document')
    completed = []
    def convert(original, scratch, cancelled, timeout):
        assert original == source and scratch != target
        assert scratch.parent.parent == target.parent
        assert not target.exists()
        if outcome == 'error':
            scratch.write_bytes(b'incomplete PDF')
            raise ValueError('Conversion failed')
        with pdf.open() as document:
            document.new_page().insert_text((20, 40), 'complete')
            document.save(scratch)
        completed.append(True)
        if outcome == 'collision':
            target.write_bytes(b'other process output')
    monkeypatch.setattr('eoingpdf.convert._convert_to_pdf', convert)
    if outcome == 'success':
        to_pdf(source, target)
        with pdf.open(target) as document:
            assert 'complete' in document[0].get_text()
    else:
        exception = {'error': ValueError, 'cancel': Cancelled, 'collision': FileExistsError}[outcome]
        with pytest.raises(exception):
            to_pdf(source, target, cancelled=lambda: outcome == 'cancel' and bool(completed))
        if outcome == 'collision':
            assert target.read_bytes() == b'other process output'
        else:
            assert not target.exists()
    assert source.read_bytes() == b'original document'
    assert not list(tmp_path.glob('.eoing-convert-*'))


def test_existing_target_is_rejected_before_conversion(tmp_path, monkeypatch):
    source, target = tmp_path / 'source.txt', tmp_path / 'result.pdf'
    source.write_text('source', encoding='utf-8')
    target.write_bytes(b'existing output')
    monkeypatch.setattr('eoingpdf.convert._convert_to_pdf', lambda *args: pytest.fail('Existing target must not be converted'))
    with pytest.raises(ValueError):
        to_pdf(source, target)
    assert target.read_bytes() == b'existing output'


def test_failed_native_partial_output_is_removed_before_fallback(tmp_path, monkeypatch):
    source, target = tmp_path / 'source.docx', tmp_path / 'result.pdf'
    source.write_bytes(b'source')
    class NativeFailure:
        returncode = 1
        def __init__(self, command, **kwargs):
            Path(command[-2]).write_bytes(b'partial native output')
            Path(command[-1]).write_text(json.dumps({'ok': False}), encoding='utf-8')
        def poll(self):
            return self.returncode
    fallback_calls = []
    def fallback(original, result, *args):
        assert not result.exists()
        fallback_calls.append(original)
        with pdf.open() as document:
            document.new_page().insert_text((20, 40), 'fallback')
            document.save(result)
    monkeypatch.setattr('eoingpdf.convert.subprocess.Popen', NativeFailure)
    monkeypatch.setattr('eoingpdf.libreoffice.find_executable', lambda: 'test-soffice')
    monkeypatch.setattr('eoingpdf.libreoffice.convert', fallback)
    to_pdf(source, target)
    assert fallback_calls == [source]
    with pdf.open(target) as document:
        assert 'fallback' in document[0].get_text()


@pytest.mark.parametrize('outcome', ['cancel', 'collision', 'copy_error'])
def test_libreoffice_publication_is_atomic(tmp_path, monkeypatch, outcome):
    from eoingpdf import libreoffice
    source, target = tmp_path / 'source.docx', tmp_path / 'result.pdf'
    source.write_bytes(b'source')
    copied = []
    real_copy = libreoffice.shutil.copyfile
    class Office:
        returncode = 0
        def __init__(self, command, **kwargs):
            output = Path(command[command.index('--outdir') + 1]) / 'source.pdf'
            with pdf.open() as document:
                document.new_page()
                document.save(output)
            if outcome == 'collision':
                target.write_bytes(b'concurrent output')
        def poll(self):
            return 0
    def copy(source_path, staged):
        if outcome == 'copy_error':
            Path(staged).write_bytes(b'incomplete copy')
            raise OSError('Disk full')
        real_copy(source_path, staged)
        copied.append(True)
    monkeypatch.setattr(libreoffice.subprocess, 'Popen', Office)
    monkeypatch.setattr(libreoffice.shutil, 'copyfile', copy)
    exception = {'cancel': Cancelled, 'collision': FileExistsError, 'copy_error': OSError}[outcome]
    with pytest.raises(exception):
        libreoffice.convert(source, target, executable='test-soffice',
                            cancelled=lambda: outcome == 'cancel' and bool(copied))
    if outcome == 'collision':
        assert target.read_bytes() == b'concurrent output'
    else:
        assert not target.exists()
    assert not list(tmp_path.glob('.eoing-lo-output-*'))
