"""Verify embedded catalogs and language propagation in the actual packaged EXE."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True, type=Path)
    executable = parser.parse_args().exe.resolve()
    with tempfile.TemporaryDirectory(prefix='frozen-languages-', dir=ROOT / 'temp') as name:
        folder = Path(name)
        source = folder / '선택 원본.pdf'
        with pdf.open() as document:
            document.new_page().insert_text((50, 60), 'Keep the original document text.')
            document.save(source)
        original = source.read_bytes()

        def run(option, packet):
            process = subprocess.run([str(executable), option], input=json.dumps(packet).encode('utf-8'),
                capture_output=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
            assert process.returncode == 0, (process.returncode, process.stderr)
            results = [json.loads(line) for line in process.stdout.splitlines() if line.startswith(b'{')]
            results = [event for event in results if event.get('type') == 'result']
            assert len(results) == 1, results
            return results[0]

        for locale, saved, occupied, unsupported, heading in (
            ('en-US', 'The output file was saved. Changes: 1',
             'The original or an existing file cannot be overwritten. Choose a new filename.',
             'Unsupported search operation.', 'Document contents'),
            ('ja-JP', '結果ファイルを保存しました。 変更項目：1',
             '元のファイルや既存のファイルには上書きできません。新しいファイル名を指定してください。',
             '対応していない検索操作です。', '文書の目次'),
        ):
            target = folder / (locale + ' 닫기 결과.pdf')
            packet = dict(source=str(source), target=str(target), operation='reverse',
                          cancel_path=str(folder / 'cancel'), locale=locale)
            result = run('--transform-child', packet)
            assert result['success'] and result['message'] == saved + '\n' + str(target), result
            content = target.read_bytes()
            with pdf.open(target) as document:
                assert document[0].get_text().strip() == 'Keep the original document text.'
            result = run('--transform-child', packet)
            assert not result['success'] and result['message'] == occupied, result
            assert target.read_bytes() == content
            result = run('--search-child', dict(mode='unknown', locale=locale))
            assert not result['success'] and result['message'] == unsupported, result
            cover = folder / (locale + '-cover.pdf')
            result = run('--transform-child', dict(packet, target=str(cover), operation='bates', bates_cover=True))
            assert result['success'], result
            with pdf.open(cover) as document:
                # Embedded fonts may extract visible spaces as U+00A0.
                extracted = ' '.join(document[0].get_text().split())
                assert len(document) == 2 and heading in extracted, (locale, len(document), extracted)
            assert source.read_bytes() == original
            print(f'PASS frozen {locale}: success/error/search catalogs, Unicode paths, contents cover and source preservation', flush=True)


if __name__ == '__main__':
    main()
