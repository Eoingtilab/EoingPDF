import importlib.util
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shell_strings', ROOT / 'scripts/generate_shell_strings.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def decode_literal(value):
    units = re.findall(r'\\x([0-9a-f]{4})', value)
    return b''.join(int(unit, 16).to_bytes(2, 'little') for unit in units).decode('utf-16-le')


def test_generated_titles_match_every_shared_catalog(tmp_path):
    output = tmp_path / 'ShellStrings.h'
    module.generate(ROOT / 'assets/locales', output)
    literals = re.findall(r'L"([^"]*)"', output.read_text(encoding='ascii'))
    expected = []
    for locale in module.LOCALES:
        catalog = json.loads((ROOT / 'assets/locales' / (locale + '.json')).read_text(encoding='utf-8'))
        expected.extend(catalog[key] for key in module.KEYS)
    assert list(map(decode_literal, literals)) == expected


def test_native_literals_escape_code_and_non_bmp_characters():
    value = 'Quote " backslash \\ newline\n tab\t 😀 한글'
    literal = module.literal(value)
    assert re.fullmatch(r'L"(?:\\x[0-9a-f]{4})*"', literal)
    assert decode_literal(literal) == value


@pytest.mark.parametrize('invalid', [None, '', 42, 'bad\0title'])
def test_invalid_catalog_does_not_replace_existing_header(tmp_path, invalid):
    data = dict.fromkeys(module.KEYS, 'Title')
    data[module.KEYS[0]] = invalid
    (tmp_path / 'ko-KR.json').write_text(json.dumps(data), encoding='utf-8')
    output = tmp_path / 'ShellStrings.h'
    output.write_text('previous')
    with pytest.raises(ValueError):
        module.generate(tmp_path, output)
    assert output.read_text() == 'previous'
