"""Build a full Microsoft Store MSIX from the verified folder distribution."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'packaging/store/AppxManifest.template.xml'
SOURCE = ROOT / 'release/EoingPDF'


def sdk_tool(name: str) -> Path:
	base = Path(r'C:\Program Files (x86)\Windows Kits\10\bin')
	versions = sorted(
		(path for path in base.glob('*') if re.fullmatch(r'\d+(?:\.\d+){3}', path.name)),
		key=lambda path: tuple(map(int, path.name.split('.'))),
		reverse=True,
	)
	for version in versions:
		candidate = version / 'x64' / name
		if candidate.is_file():
			return candidate
	raise FileNotFoundError(f'Windows SDK tool not found: {name}')


def package_version(version: str) -> str:
	parts = version.strip().split('.')
	if len(parts) != 3 or any(not part.isdigit() for part in parts):
		raise ValueError('VERSION must be semantic x.y.z for Store packaging')
	values = [int(part) for part in parts]
	if any(value < 0 or value > 65535 for value in values):
		raise ValueError('Store package version component out of range')
	return '.'.join(map(str, values)) + '.0'


def validate_identity(package_name: str, publisher: str, publisher_display_name: str) -> None:
	if not package_name or len(package_name) > 50:
		raise ValueError('Partner Center package identity name is required (max 50 chars)')
	if not re.fullmatch(r'[A-Za-z0-9.-]+', package_name):
		raise ValueError('Package identity name contains unsupported characters')
	if not publisher.startswith('CN=') or len(publisher) > 8192:
		raise ValueError('Exact Partner Center Publisher value is required')
	if not publisher_display_name.strip():
		raise ValueError('Publisher display name is required')


def render_manifest(target: Path, package_name: str, publisher: str, publisher_display_name: str, version: str) -> None:
	validate_identity(package_name, publisher, publisher_display_name)
	text = TEMPLATE.read_text(encoding='utf-8-sig')
	replacements = {
		'__PACKAGE_NAME__': package_name,
		'__PUBLISHER__': publisher,
		'__PUBLISHER_DISPLAY_NAME__': publisher_display_name,
		'__VERSION__': package_version(version),
	}
	for key, value in replacements.items():
		text = text.replace(key, value)
	target.write_text(text, encoding='utf-8')
	ET.parse(target)


def square_icon(source: Image.Image, size: int) -> Image.Image:
	canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
	image = source.copy()
	image.thumbnail((size, size), Image.Resampling.LANCZOS)
	x = (size - image.width) // 2
	y = (size - image.height) // 2
	canvas.alpha_composite(image, (x, y))
	return canvas


def wide_icon(source: Image.Image, width: int, height: int) -> Image.Image:
	canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
	image = source.copy()
	image.thumbnail((height, height), Image.Resampling.LANCZOS)
	x = (width - image.width) // 2
	y = (height - image.height) // 2
	canvas.alpha_composite(image, (x, y))
	return canvas


def write_assets(folder: Path) -> None:
	assets = folder / 'Assets'
	assets.mkdir(parents=True, exist_ok=True)
	with Image.open(ROOT / 'assets/app_icon.png') as opened:
		source = opened.convert('RGBA')
		square_icon(source, 50).save(assets / 'StoreLogo.png')
		square_icon(source, 44).save(assets / 'Square44x44Logo.png')
		square_icon(source, 150).save(assets / 'Square150x150Logo.png')
		square_icon(source, 310).save(assets / 'Square310x310Logo.png')
		wide_icon(source, 310, 150).save(assets / 'Wide310x150Logo.png')


def assert_ascii_paths(folder: Path) -> None:
	invalid = []
	for path in folder.rglob('*'):
		try:
			str(path.relative_to(folder)).encode('ascii')
		except UnicodeEncodeError:
			invalid.append(str(path.relative_to(folder)))
	if invalid:
		raise ValueError('Microsoft Store package contains non-ASCII filenames: ' + ', '.join(invalid[:10]))


def build(output: Path, package_name: str, publisher: str, publisher_display_name: str, source: Path = SOURCE, makeappx: Path | None = None) -> Path:
	source = source.resolve()
	if not (source / 'EoingPDF.exe').is_file():
		raise FileNotFoundError(f'Verified folder distribution missing: {source / "EoingPDF.exe"}')
	if not (source / 'EoingPDF.Explorer.dll').is_file():
		raise FileNotFoundError('EoingPDF.Explorer.dll is required for Store context menus')
	version = (ROOT / 'VERSION').read_text(encoding='utf-8-sig').strip()
	output = output.resolve()
	output.parent.mkdir(parents=True, exist_ok=True)
	tool = makeappx or sdk_tool('makeappx.exe')
	with tempfile.TemporaryDirectory(prefix='eoingpdf-store-', dir=output.parent) as temporary:
		stage = Path(temporary) / 'content'
		shutil.copytree(source, stage)
		for obsolete in ('install-context-menu.cmd', 'uninstall-context-menu.cmd'):
			(stage / obsolete).unlink(missing_ok=True)
		render_manifest(stage / 'AppxManifest.xml', package_name, publisher, publisher_display_name, version)
		write_assets(stage)
		assert_ascii_paths(stage)
		draft = Path(temporary) / output.name
		subprocess.run(
			[str(tool), 'pack', '/o', '/d', str(stage), '/p', str(draft)],
			check=True,
			timeout=600,
			creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
		)
		with zipfile.ZipFile(draft) as archive:
			if archive.testzip():
				raise ValueError('MSIX archive CRC validation failed')
			names = set(archive.namelist())
			required = {'AppxManifest.xml', 'AppxBlockMap.xml', 'EoingPDF.exe', 'EoingPDF.Explorer.dll'}
			if not required.issubset(names):
				raise ValueError('MSIX missing required files: ' + ', '.join(sorted(required - names)))
		os.replace(draft, output)
	return output


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--package-name', required=True, help='Exact Package/Identity/Name from Partner Center')
	parser.add_argument('--publisher', required=True, help='Exact Package/Identity/Publisher from Partner Center')
	parser.add_argument('--publisher-display-name', required=True)
	parser.add_argument('--source', type=Path, default=SOURCE)
	parser.add_argument('--output', type=Path)
	parser.add_argument('--makeappx', type=Path)
	args = parser.parse_args()
	version = (ROOT / 'VERSION').read_text(encoding='utf-8-sig').strip()
	output = args.output or ROOT / f'release/EoingPDF-{version}-Store-x64.msix'
	print(build(output, args.package_name, args.publisher, args.publisher_display_name, args.source, args.makeappx))


if __name__ == '__main__':
	main()
