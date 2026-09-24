import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('modern_shell_package', ROOT / 'scripts/package_modern_shell.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_generated_identity_matches_native_commands_and_uses_external_content(tmp_path):
    builder.generate_manifest(tmp_path, '2.2.0', 'CN=Eoingtilab')
    root = ET.parse(tmp_path / 'AppxManifest.xml').getroot()
    namespace = builder.NAMESPACES
    assert root.find('Identity', namespace).attrib == {
        'Name': 'Eoingtilab.EoingPDF.Shell', 'Publisher': 'CN=Eoingtilab',
        'Version': '2.2.0.0', 'ProcessorArchitecture': 'x64'}
    assert root.find('Properties/uap10:AllowExternalContent', namespace).text == 'true'
    classes = root.findall('.//com:Class', namespace)
    verbs = root.findall('.//desktop5:Verb', namespace)
    expected = {f'71BC7F3A-9D38-4AD1-B76C-9B3E1EA4500{i}' for i in (1, 2, 3)}
    assert {entry.attrib['Id'] for entry in classes} == expected
    assert {entry.attrib['Clsid'] for entry in verbs} == expected
    assert all(entry.attrib['Path'] == 'EoingPDF.Explorer.dll' for entry in classes)
    application = root.find('Applications/Application', namespace)
    assert application.attrib['Executable'] == 'EoingPDF.exe'
    assert application.find('uap:VisualElements', namespace).attrib['AppListEntry'] == 'none'
    for name, size in [('StoreLogo', 50), ('Square150x150Logo', 150), ('Square44x44Logo', 44)]:
        with Image.open(tmp_path / 'Assets' / (name + '.png')) as icon:
            assert icon.size == (size, size) and icon.mode == 'RGBA'


@pytest.mark.parametrize('version,publisher', [('2.2', 'CN=App'), ('65536.0.0', 'CN=App'), ('2.2.0', ''), ('2.2.0', 'CN=App\n')])
def test_invalid_identity_never_creates_manifest(tmp_path, version, publisher):
    with pytest.raises(ValueError):
        builder.generate_manifest(tmp_path, version, publisher)
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows SDK MakeAppx')
def test_actual_sdk_build_contains_identity_and_icons_without_app_payload(tmp_path):
    target = builder.build(tmp_path / 'shell.msix', 'CN=Eoingtilab')
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert 'AppxManifest.xml' in names and 'AppxBlockMap.xml' in names
        assert 'AppxSignature.p7x' not in names
        assert not any(name.lower().endswith(('.exe', '.dll', '.pfx')) for name in names)
        assert sum(name.lower().endswith('.png') for name in names) == 3
    assert list(tmp_path.iterdir()) == [target]
