import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pytest
from eoingpdf.quick import read_manifest

def test_manifest_bounded_and_valid(tmp_path):
    local = tmp_path / 'local'
    queue = local / 'EoingPDF' / 'queue'
    queue.mkdir(parents=True)
    file = tmp_path / '한글.pdf'
    file.write_bytes(b'%PDF')
    manifest = queue / 'a.files'
    manifest.write_text(f'\n{file}\n', encoding='utf-8')
    assert read_manifest(manifest, local) == [str(file.resolve())]

def test_manifest_rejects_path_and_wrong_owner(tmp_path):
    local = tmp_path / 'local'
    queue = local / 'EoingPDF' / 'queue'
    queue.mkdir(parents=True)
    manifest = queue / 'a.files'
    manifest.write_text(str(tmp_path / 'missing.pdf'), encoding='utf-8')
    with pytest.raises(ValueError): read_manifest(manifest, local)
    with pytest.raises(ValueError): read_manifest(tmp_path / 'a.files', local)


def test_manifest_handles_virtualized_final_file_path_without_broadening_queue(tmp_path, monkeypatch):
    local = tmp_path / 'local'
    queue = local / 'EoingPDF/queue'
    queue.mkdir(parents=True)
    source = tmp_path / 'document.pdf'
    source.write_bytes(b'%PDF')
    manifest = queue / 'job.files'
    manifest.write_text(str(source), encoding='utf-8')
    original = Path.resolve
    def virtualized(path, *args, **kwargs):
        if path == manifest:
            return tmp_path / 'package/LocalCache/job.files'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'resolve', virtualized)
    assert read_manifest(manifest, local) == [str(source.resolve())]
    outside = queue.parent / 'outside.files'
    outside.write_text(str(source), encoding='utf-8')
    with pytest.raises(ValueError):
        read_manifest(queue / '..' / 'outside.files', local)
