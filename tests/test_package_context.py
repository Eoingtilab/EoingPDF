from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from eoingpdf import package_context


def test_package_context_override(monkeypatch):
	monkeypatch.setenv('EOINGPDF_TEST_PACKAGE_FULL_NAME', 'Eoingtilab.EoingPDF_2.2.2.0_x64__test')
	assert package_context.is_packaged()
	assert package_context.store_managed_updates()


def test_package_context_empty_override(monkeypatch):
	monkeypatch.setenv('EOINGPDF_TEST_PACKAGE_FULL_NAME', '')
	assert package_context.package_full_name() is None
	assert not package_context.is_packaged()
