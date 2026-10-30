from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('store_package', ROOT / 'scripts/package_store_msix.py')
store_package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store_package)

NS = {
	'p': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
	'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
	'uap10': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/10',
	'rescap': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities',
	'desktop4': 'http://schemas.microsoft.com/appx/manifest/desktop/windows10/4',
}


def test_store_manifest_uses_partner_center_identity_and_store_safe_runtime(tmp_path):
	target = tmp_path / 'AppxManifest.xml'
	store_package.render_manifest(
		target,
		'12345Eoingtilab.EoingPDF',
		'CN=01234567-89AB-CDEF-0123-456789ABCDEF',
		'Eoingti Lab',
		'2.2.2',
	)
	root = ET.parse(target).getroot()
	identity = root.find('p:Identity', NS)
	assert identity.attrib['Name'] == '12345Eoingtilab.EoingPDF'
	assert identity.attrib['Publisher'] == 'CN=01234567-89AB-CDEF-0123-456789ABCDEF'
	assert identity.attrib['Version'] == '2.2.2.0'
	app = root.find('p:Applications/p:Application', NS)
	assert app.attrib['Executable'] == 'EoingPDF.exe'
	assert app.attrib[f"{{{NS['uap10']}}}RuntimeBehavior"] == 'win32App'
	assert root.find(".//uap:FileTypeAssociation[@Name='eoingpdf.pdf']", NS) is not None
	assert root.find(".//desktop4:Extension[@Category='windows.fileExplorerContextMenus']", NS) is not None
	caps = [item.attrib['Name'] for item in root.findall('p:Capabilities/rescap:Capability', NS)]
	assert caps == ['runFullTrust']
	text = target.read_text(encoding='utf-8')
	assert 'unvirtualizedResources' not in text
	assert 'AllowExternalContent' not in text


@pytest.mark.parametrize('value', ['2.2', '2.2.2.1', '2.x.2', '70000.1.1'])
def test_package_version_rejects_invalid_values(value):
	with pytest.raises(ValueError):
		store_package.package_version(value)
