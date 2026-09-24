import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pytest
from PIL import Image, ImageDraw
import pymupdf as pdf
from eoingpdf.seal_vault import SealVault, read_seal
from eoingpdf.advanced import transform

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows DPAPI required')


@pytest.fixture
def image(tmp_path):
    path = tmp_path / 'seal.png'
    picture = Image.new('RGB', (100, 60), 'white')
    ImageDraw.Draw(picture).rectangle((5, 5, 95, 55), outline='red', width=6)
    picture.save(path)
    return path


def test_real_dpapi_reopen_and_stamp(tmp_path, image):
    vault = SealVault(tmp_path / 'vault')
    saved = vault.add(image, '개인 서명')
    blob = saved.read_bytes()
    assert b'PNG' not in blob and '개인 서명'.encode() not in blob
    name, stream = read_seal(saved)
    assert name == '개인 서명' and stream.startswith(b'\x89PNG')
    assert SealVault(vault.folder).entries() == [(saved, name, True)]
    source, target = tmp_path / 'source.pdf', tmp_path / 'stamped.pdf'
    with pdf.open() as document:
        document.new_page(width=300, height=300)
        document.save(source)
    transform(source, target, 'stamp', watermark_image=str(saved))
    with pdf.open(target) as document:
        assert len(document[0].get_images()) == 1
    assert list(vault.folder.iterdir()) == [saved]
    assert saved.read_bytes() == blob


def test_tamper_and_delete_boundary(tmp_path, image):
    vault = SealVault(tmp_path / 'vault')
    saved = vault.add(image, '업무용')
    saved.write_bytes(saved.read_bytes()[:-10] + b'broken')
    with pytest.raises(ValueError, match='열 수 없습니다'):
        read_seal(saved)
    assert vault.entries()[0][2] is False
    with pytest.raises(ValueError, match='보관함 안'):
        vault.remove(image)
    assert image.exists()
    vault.remove(saved)
    assert not vault.entries() and image.exists()


@pytest.mark.parametrize('name', ('', ' ', 'x' * 81, 'a\nb'))
def test_invalid_name_no_file(tmp_path, image, name):
    vault = SealVault(tmp_path / 'vault')
    with pytest.raises(ValueError):
        vault.add(image, name)
    assert not vault.folder.exists()
