import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.shell import registration_status, IDS

def test_registration_status_is_read_only_and_complete(tmp_path):
    result = registration_status(tmp_path / 'portable')
    assert set(result) == {'folder', 'pdf_open', 'actions', 'owner', 'ready'}
    assert result['folder'] == str((tmp_path / 'portable').resolve())
    assert set(result['actions']) == set(IDS)
    assert result['ready'] is False
