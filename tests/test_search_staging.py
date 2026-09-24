import os
import json
from pathlib import Path
import subprocess
import sys
import pymupdf as pdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.search_staging import prepare, complete, delete_index
from eoingpdf.semantic_search import LocalEmbedder, PdfSearchIndex, SearchCancelled


@pytest.fixture
def files(tmp_path):
    model = ROOT / 'temp/search-model/external'
    if not (model / 'model.onnx').is_file():
        pytest.skip('Prepare external ONNX evaluation model first')
    folder = tmp_path / 'docs'; folder.mkdir()
    with pdf.open() as document:
        document.new_page().insert_text((72, 72), 'Reset account password through email verification.')
        document.save(folder / 'guide.pdf')
    return model, folder, tmp_path / 'search.db', tmp_path / 'staged.db'


def test_real_separate_processes_do_not_load_both_engines(files):
    model, folder, database, staged = files
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    prefix = "import sys,json; sys.path.insert(0,sys.argv[1]); from eoingpdf.search_staging import prepare,complete; "
    commands = [
        "r=prepare(*sys.argv[2:]); assert 'onnxruntime' not in sys.modules; print(json.dumps(r))",
        "r=complete(sys.argv[2],sys.argv[4],sys.argv[5]); assert 'pymupdf' not in sys.modules; print(json.dumps(r))",
    ]
    for command in commands:
        result = subprocess.run([sys.executable, '-c', prefix + command, str(ROOT / 'src'),
            str(model), str(folder), str(database), str(staged)], env=environment,
            capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)
    assert database.exists() and not staged.exists()
    index = PdfSearchIndex(database, LocalEmbedder(model))
    assert index.search('Forgot login credentials')[0]['page'] == 0


def test_pending_index_cancel_and_conflicting_publication(files):
    model, folder, database, staged = files
    prepare(model, folder, database, staged)
    embedder = LocalEmbedder(model)
    with pytest.raises(ValueError, match='아직'):
        PdfSearchIndex(staged, embedder).search('password')
    with pytest.raises(SearchCancelled):
        complete(model, database, staged, cancelled=lambda: True)
    assert not database.exists() and staged.exists()
    database.write_bytes(b'another job changed the destination')
    with pytest.raises(ValueError, match='다른 검색'):
        complete(model, database, staged)
    assert database.read_bytes() == b'another job changed the destination'


def test_delete_index_rejects_noncache_and_outside_paths(tmp_path):
    cache = tmp_path / 'cache'; cache.mkdir()
    user_file = cache / 'personal.pdf'; user_file.write_bytes(b'preserve')
    with pytest.raises(ValueError):
        delete_index(user_file, cache)
    outside = tmp_path / ('a' * 64 + '.sqlite3'); outside.write_bytes(b'preserve')
    with pytest.raises(ValueError):
        delete_index(outside, cache)
    assert user_file.read_bytes() == outside.read_bytes() == b'preserve'
    own = cache / ('b' * 64 + '.sqlite3'); own.write_bytes(b'index')
    delete_index(own, cache)
    assert not own.exists()
    delete_index(own, cache)


def test_deletion_invalidates_an_already_prepared_rebuild(files):
    model, folder, old_database, staged = files
    database = old_database.parent / ('c' * 64 + '.sqlite3')
    prepare(model, folder, database, staged)
    complete(model, database, staged)
    prepare(model, folder, database, staged)
    delete_index(database, database.parent)
    with pytest.raises(ValueError, match='다른 검색'):
        complete(model, database, staged)
    assert not database.exists()
