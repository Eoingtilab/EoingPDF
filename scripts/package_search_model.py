"""Stage only verified, pinned local search assets; never download at app startup."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
HASHES = {
    'model.onnx': '18cc61ddb009c027742870cb501a3b56dab1c514814a985fc4570b07f26cdee1',
    'weights.bin': '9799f4dde06830548c00d19ca7f93601f2e687cc8e905592c9cdb6b70635eaf3',
    'tokenizer.json': '11aaf894a4ccf3d95e8830e27c0f8152791fbbff2b988e29a265580b86edd216',
}


def verify(folder):
    for name, expected in HASHES.items():
        with (folder / name).open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError(f'Pinned search asset mismatch: {name}')
    metadata = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
    if metadata.get('revision') != 'b68f4122911bcffcd6e1f695f2d99cd6788972d8':
        raise ValueError('Unexpected model revision')
    for name, field in [('model.onnx', 'model_sha256'), ('weights.bin', 'weights_sha256'),
                        ('tokenizer.json', 'tokenizer_sha256')]:
        if metadata.get(field) != HASHES[name]:
            raise ValueError('Model provenance does not match pinned files')


def main():
    if '--verify' in sys.argv:
        verify(ROOT / 'assets/search')
        for name in ('MODEL_CARD.md', 'LICENSE-Apache-2.0.txt', 'MODIFICATIONS.txt'):
            if not (ROOT / 'assets/search' / name).is_file():
                raise ValueError(f'Missing search model notice: {name}')
        print('Packaged search assets verified')
        return
    source = ROOT / 'temp/search-model/external'
    verify(source)
    target = ROOT / 'assets/search'
    target.mkdir(parents=True, exist_ok=True)
    for name in (*HASHES, 'provenance.json'):
        shutil.copyfile(source / name, target / name)
    shutil.copyfile(source.parent / 'MODEL_CARD.md', target / 'MODEL_CARD.md')
    distribution = importlib.metadata.distribution('onnx')
    license_path = distribution.locate_file('onnx-1.22.0.dist-info/licenses/LICENSE')
    shutil.copyfile(license_path, target / 'LICENSE-Apache-2.0.txt')
    (target / 'MODIFICATIONS.txt').write_text(
        'EoingPDF uses the first 256 Matryoshka dimensions with per-token symmetric int8 quantization.\n'
        'The ONNX graph gathers tokens, dequantizes, averages and normalizes locally.\n'
        'Source revision and file hashes are recorded in provenance.json.\n'
        'Retrieval quality remains under evaluation; consult docs/SEARCH_MODEL_EVALUATION.md.\n', encoding='utf-8')
    verify(target)
    print(f'Verified search assets: {target}')


if __name__ == '__main__':
    main()
