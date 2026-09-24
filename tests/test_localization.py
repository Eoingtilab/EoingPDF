import sys
import json
from string import Formatter
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.localization import load_catalog, normalize_locale, system_locale


def test_locale_selection_and_path_safety():
    assert normalize_locale('en_GB') == 'en-US'
    assert normalize_locale('ja-JP') == 'ja-JP'
    assert normalize_locale('../../secrets') == 'ko-KR'
    with patch('eoingpdf.localization.sys.platform', 'win32'), patch('eoingpdf.localization.ctypes.windll') as library:
        library.kernel32.GetUserDefaultUILanguage.return_value = 0x0411
        assert system_locale() == 'ja-JP'
        library.kernel32.GetUserDefaultUILanguage.return_value = 0x0409
        assert system_locale() == 'en-US'


def test_resource_key_and_placeholder_parity():
    folder = Path(__file__).resolve().parents[1] / 'assets/locales'
    catalogs = [json.loads((folder / f'{locale}.json').read_text(encoding='utf-8'))
                for locale in ('ko-KR', 'en-US', 'ja-JP')]
    assert all(catalog.keys() == catalogs[0].keys() for catalog in catalogs)
    assert catalogs[1]['일반'] == 'General'
    assert catalogs[2]['일반'] == '一般'
    assert all('{version}' in catalog['현재 버전: {version}'] for catalog in catalogs)
    from eoingpdf.licensing import ERRORS
    assert all(message in catalogs[0] for message in ERRORS.values())
    def fields(value):
        return sorted((name, spec, conversion or '') for _, name, spec, conversion in Formatter().parse(value)
                      if name is not None)
    for key in catalogs[0]:
        for catalog in catalogs:
            assert fields(catalog[key]) == fields(key), key


def test_missing_and_corrupt_resource_fallback(tmp_path):
    (tmp_path / 'ko-KR.json').write_text(json.dumps({'key': '한국어'}), encoding='utf-8')
    (tmp_path / 'en-US.json').write_text('{broken', encoding='utf-8')
    assert load_catalog('en-US', tmp_path) == {'key': '한국어'}
    assert load_catalog('ja-JP', tmp_path) == {'key': '한국어'}
