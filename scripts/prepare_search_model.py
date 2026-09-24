"""Build a pinned, local-only quantized embedding model for evaluation."""
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import argparse

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'sentence-transformers/static-similarity-mrl-multilingual-v1'
REVISION = 'b68f4122911bcffcd6e1f695f2d99cd6788972d8'
BASE = f'https://huggingface.co/{MODEL}/resolve/{REVISION}/'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(name, target, expected=None):
    if target.exists() and (expected is None or digest(target) == expected):
        return
    partial = target.with_suffix('.download')
    try:
        with urllib.request.urlopen(BASE + name, timeout=60) as response, partial.open('wb') as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
        if expected and digest(partial) != expected:
            raise ValueError('Model checksum mismatch')
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--external', action='store_true')
    args = parser.parse_args()
    import numpy as np
    import onnx
    from onnx import helper as h, numpy_helper as nh, TensorProto as T
    from safetensors import safe_open
    folder = ROOT / 'temp/search-model'
    folder.mkdir(parents=True, exist_ok=True)
    weights = folder / 'source.safetensors'
    download('0_StaticEmbedding/model.safetensors', weights,
             '8245ab78ee71dded845a82d2270fcb9e785b29dad0e1619f69d5390c47d9ba00')
    download('0_StaticEmbedding/tokenizer.json', folder / 'tokenizer.json',
             '11aaf894a4ccf3d95e8830e27c0f8152791fbbff2b988e29a265580b86edd216')
    download('README.md', folder / 'MODEL_CARD.md')
    with safe_open(weights, framework='numpy') as source:
        keys = list(source.keys())
        if len(keys) != 1:
            raise ValueError(f'Unexpected weights: {keys}')
        matrix = source.get_slice(keys[0])[:, :256].copy()
    if matrix.shape != (105879, 256) or not np.isfinite(matrix).all():
        raise ValueError('Unexpected embedding shape or values')
    scale = np.maximum(np.max(np.abs(matrix), axis=1, keepdims=True) / 127, 1e-12).astype(np.float32)
    quantized = np.rint(matrix / scale).clip(-127, 127).astype(np.int8)
    # Gather before dequantization so no full float table is allocated at runtime.
    nodes = [h.make_node('Gather', ['weights', 'ids'], ['rows'], axis=0),
             h.make_node('Gather', ['scales', 'ids'], ['row_scales'], axis=0),
             h.make_node('Cast', ['rows'], ['floats'], to=T.FLOAT),
             h.make_node('Mul', ['floats', 'row_scales'], ['tokens']),
             h.make_node('ReduceMean', ['tokens', 'axis0'], ['mean'], keepdims=0),
             h.make_node('ReduceL2', ['mean', 'axis0'], ['norm'], keepdims=1),
             h.make_node('Max', ['norm', 'epsilon'], ['denominator']),
             h.make_node('Div', ['mean', 'denominator'], ['embedding'])]
    constants = [nh.from_array(quantized, 'weights'), nh.from_array(scale, 'scales'),
                 nh.from_array(np.array([0], dtype=np.int64), 'axis0'),
                 nh.from_array(np.array([1e-12], dtype=np.float32), 'epsilon')]
    graph = h.make_graph(nodes, 'EoingPDF local static embeddings',
        [h.make_tensor_value_info('ids', T.INT64, ['tokens'])],
        [h.make_tensor_value_info('embedding', T.FLOAT, [256])], constants)
    model = h.make_model(graph, opset_imports=[h.make_opsetid('', 18)], ir_version=10,
                         producer_name='EoingPDF')
    onnx.checker.check_model(model)
    output = folder / 'external' if args.external else folder
    output.mkdir(exist_ok=True)
    target = output / 'model.onnx'
    if args.external:
        (output / 'weights.bin').unlink(missing_ok=True)
        onnx.save_model(model, target, save_as_external_data=True, all_tensors_to_one_file=True,
                        location='weights.bin', size_threshold=1024)
        shutil.copyfile(folder / 'tokenizer.json', output / 'tokenizer.json')
    else:
        onnx.save_model(model, target)
    metadata = dict(source=MODEL, revision=REVISION, license='Apache-2.0', dimensions=256,
        quantization='per-token symmetric int8', model_sha256=digest(target),
        tokenizer_sha256=digest(folder / 'tokenizer.json'), status='evaluation-only')
    if args.external:
        metadata['weights_sha256'] = digest(output / 'weights.bin')
    (output / 'provenance.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata), flush=True)
    print(f'Model bytes: {target.stat().st_size}', flush=True)


if __name__ == '__main__':
    main()
