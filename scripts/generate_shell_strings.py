"""Compile shared locale catalogs into UTF-16 literals for the native shell DLL."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('어잉PDF · 하나로 합치기', '어잉PDF · PDF로 변환', '어잉PDF · 핵심문장 요약')
LOCALES = ('ko-KR', 'en-US', 'ja-JP')


def literal(value):
    # Encode individual UTF-16 units, including surrogate pairs. Fixed four-digit
    # octal-free escapes prevent quotes, backslashes or newlines becoming code.
    encoded = value.encode('utf-16-le')
    return 'L"' + ''.join('\\x%04x' % int.from_bytes(encoded[i:i + 2], 'little')
                          for i in range(0, len(encoded), 2)) + '"'


def generate(catalogs, output):
    rows = []
    for locale in LOCALES:
        data = json.loads((Path(catalogs) / (locale + '.json')).read_text(encoding='utf-8-sig'))
        values = [data.get(key) for key in KEYS]
        if any(not isinstance(value, str) or not value.strip() or '\0' in value for value in values):
            raise ValueError(f'{locale}: missing or invalid shell title')
        rows.append('    {' + ', '.join(literal(value) for value in values) + '}')
    content = ('// Generated from assets/locales; do not edit.\n#pragma once\n'
               'static const wchar_t* const shellTitles[3][3] = {\n'
               + ',\n'.join(rows) + '\n};\n')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding='ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogs', type=Path, default=ROOT / 'assets/locales')
    parser.add_argument('--output', type=Path, default=ROOT / 'temp/ShellStrings.h')
    args = parser.parse_args()
    generate(args.catalogs, args.output)


if __name__ == '__main__':
    main()
