"""Local ONNX embeddings and transactional PDF passage indexing."""
from .localization import tr
import hashlib
import heapq
import json
import math
from pathlib import Path
import sqlite3


class SearchCancelled(Exception):
    pass


def fingerprint(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class ModelFiles:
    dimensions = 256

    def __init__(self, folder):
        folder = Path(folder)
        metadata = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
        for name, field in [('model.onnx', 'model_sha256'), ('tokenizer.json', 'tokenizer_sha256')]:
            if fingerprint(folder / name) != metadata[field]:
                raise ValueError(tr('검색 모델 파일이 손상되었습니다.'))
        if metadata.get('dimensions') != self.dimensions:
            raise ValueError(tr('지원하지 않는 검색 모델 차원입니다.'))
        self.identity = metadata['model_sha256'] + ':' + metadata['tokenizer_sha256']
        if 'weights_sha256' in metadata:
            if fingerprint(folder / 'weights.bin') != metadata['weights_sha256']:
                raise ValueError(tr('검색 모델 가중치 파일이 손상되었습니다.'))
            self.identity += ':' + metadata['weights_sha256']


class LocalEmbedder(ModelFiles):
    def __init__(self, folder):
        super().__init__(folder)
        import onnxruntime as ort
        from tokenizers import Tokenizer
        folder = Path(folder)
        self.tokenizer = Tokenizer.from_file(str(folder / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=2048)
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = options.enable_mem_pattern = False
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        self.session = ort.InferenceSession(str(folder / 'model.onnx'), sess_options=options,
                                            providers=['CPUExecutionProvider'])

    def encode(self, text):
        import numpy as np
        if not isinstance(text, str) or len(text) > 20000:
            raise ValueError(tr('검색 문장이 너무 길거나 올바르지 않습니다.'))
        ids = self.tokenizer.encode(text, add_special_tokens=False).ids
        if not ids:
            return np.zeros(self.dimensions, dtype=np.float32)
        vector = self.session.run(['embedding'], {'ids': np.asarray(ids, dtype=np.int64)})[0]
        if vector.shape != (self.dimensions,) or not np.isfinite(vector).all():
            raise ValueError(tr('검색 모델이 올바른 결과를 반환하지 않았습니다.'))
        return vector


class PdfSearchIndex:
    """One folder per index; text and coordinates stay in the caller's local DB."""
    def __init__(self, database, embedder):
        self.database = Path(database)
        self.embedder = embedder

    def connect(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, timeout=5)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA cache_size=-2048')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents (path TEXT PRIMARY KEY, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS passages (
                id INTEGER PRIMARY KEY, path TEXT NOT NULL REFERENCES documents(path) ON DELETE CASCADE,
                page INTEGER NOT NULL, rect TEXT NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL);
            CREATE INDEX IF NOT EXISTS passage_path ON passages(path);
        ''')
        return connection

    def build(self, folder, cancelled=lambda: False, progress=lambda done, total: None, *, defer_embeddings=False, use_ocr=False):
        import pymupdf as pdf
        folder = Path(folder).resolve(strict=True)
        if not folder.is_dir():
            raise ValueError(tr('검색할 폴더를 선택해 주세요.'))
        paths = []
        for path in folder.rglob('*'):
            if cancelled():
                raise SearchCancelled()
            if path.suffix.lower() == '.pdf' and path.is_file() and not path.is_symlink():
                resolved = path.resolve()
                if resolved.is_relative_to(folder):
                    paths.append(resolved)
                if len(paths) > 2000:
                    raise ValueError(tr('한 번에 최대 2,000개 PDF를 색인할 수 있습니다.'))
        paths = sorted(set(paths))
        connection = self.connect()
        errors, updated, reused = [], 0, 0
        try:
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                metadata = dict(connection.execute('SELECT key,value FROM metadata'))
                identity = self.embedder.identity
                policy = 'ocr-v2' if use_ocr else 'native-v1'
                if metadata.get('model') != identity or metadata.get('folder') != str(folder) or metadata.get('text_policy') != policy:
                    connection.execute('DELETE FROM documents')
                for key, value in [('model', identity), ('folder', str(folder)), ('text_policy', policy)]:
                    connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, value))
                present = {str(path) for path in paths}
                for (old,) in connection.execute('SELECT path FROM documents').fetchall():
                    if old not in present:
                        connection.execute('DELETE FROM documents WHERE path=?', (old,))
                count = connection.execute('SELECT COUNT(*) FROM passages').fetchone()[0]
                for index, path in enumerate(paths):
                    if cancelled():
                        raise SearchCancelled()
                    key = str(path)
                    try:
                        before = fingerprint(path)
                        existing = connection.execute('SELECT digest FROM documents WHERE path=?', (key,)).fetchone()
                        if existing == (before,):
                            reused += 1
                            progress(index + 1, len(paths))
                            continue
                        old_count = connection.execute('SELECT COUNT(*) FROM passages WHERE path=?', (key,)).fetchone()[0]
                        connection.execute('DELETE FROM documents WHERE path=?', (key,))
                        count -= old_count
                        connection.execute('SAVEPOINT document')
                        with pdf.open(path) as document:
                            if document.needs_pass:
                                raise ValueError(tr('암호가 필요한 문서입니다.'))
                            if not document.is_pdf or len(document) > 10000:
                                raise ValueError(tr('페이지가 너무 많거나 PDF 형식이 아닙니다.'))
                            connection.execute('INSERT INTO documents VALUES (?,?)', (key, before))
                            added = 0
                            for page_number, page in enumerate(document):
                                if cancelled():
                                    raise SearchCancelled()
                                from .search_text import page_blocks
                                for block in page_blocks(page, use_ocr, cancelled):
                                    if block[6] != 0 or not block[4].strip():
                                        continue
                                    text = block[4].strip()
                                    rect = json.dumps(list(block[:4]))
                                    for offset in range(0, len(text), 1000):
                                        if cancelled():
                                            raise SearchCancelled()
                                        if count + added >= 100000:
                                            raise ValueError(tr('색인 구간이 100,000개를 초과했습니다.'))
                                        passage = text[offset:offset + 1000]
                                        vector = b'' if defer_embeddings else self.embedder.encode(passage).astype('<f4').tobytes()
                                        connection.execute('INSERT INTO passages(path,page,rect,text,vector) VALUES (?,?,?,?,?)',
                                            (key, page_number, rect, passage, vector))
                                        added += 1
                        if fingerprint(path) != before:
                            raise ValueError(tr('색인 중 문서가 변경되었습니다. 다시 검색해 주세요.'))
                        connection.execute('RELEASE document')
                        count += added
                        updated += 1
                    except (OSError, ValueError, RuntimeError) as error:
                        # Remove a changed document's previous passages rather than serve stale content.
                        try:
                            connection.execute('ROLLBACK TO document')
                            connection.execute('RELEASE document')
                        except sqlite3.OperationalError:
                            pass
                        connection.execute('DELETE FROM documents WHERE path=?', (key,))
                        errors.append({'path': key, 'message': str(error)})
                    progress(index + 1, len(paths))
                connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
                                   ('state', 'pending' if defer_embeddings else 'ready'))
            return dict(updated=updated, reused=reused, errors=errors, files=len(paths))
        finally:
            connection.close()

    def search(self, query, limit=10, cancelled=lambda: False):
        import numpy as np
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ValueError(tr('검색어를 1~2,000자로 입력해 주세요.'))
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError(tr('검색 결과 수는 1~100이어야 합니다.'))
        connection = self.connect()
        try:
            state = connection.execute("SELECT value FROM metadata WHERE key='state'").fetchone()
            if state == ('pending',):
                raise ValueError(tr('검색 색인 계산이 아직 끝나지 않았습니다.'))
            identity = connection.execute("SELECT value FROM metadata WHERE key='model'").fetchone()
            if identity != (self.embedder.identity,):
                raise ValueError(tr('검색 모델이 바뀌었습니다. 폴더를 다시 색인해 주세요.'))
            query_vector = self.embedder.encode(query)
            heap, current_files = [], {}
            for identifier, path, page, rect, text, blob, digest in connection.execute(
                    'SELECT p.id,p.path,p.page,p.rect,p.text,p.vector,d.digest FROM passages p JOIN documents d ON p.path=d.path'):
                if cancelled():
                    raise SearchCancelled()
                if len(blob) != self.embedder.dimensions * 4:
                    raise ValueError(tr('검색 색인이 손상되었습니다. 다시 색인해 주세요.'))
                score = float(np.frombuffer(blob, dtype='<f4') @ query_vector)
                if not math.isfinite(score):
                    raise ValueError(tr('검색 색인에 잘못된 점수가 있습니다.'))
                entry = (score, identifier, path, page, rect, text, digest)
                if len(heap) >= limit * 5 and entry[:2] <= heap[0][:2]:
                    continue
                if path not in current_files:
                    try:
                        current_files[path] = fingerprint(path)
                    except OSError:
                        current_files[path] = None
                if current_files[path] != digest:
                    continue
                if len(heap) < limit * 5:
                    heapq.heappush(heap, entry)
                elif entry[:2] > heap[0][:2]:
                    heapq.heapreplace(heap, entry)
            results, checked = [], {}
            for score, _, path, page, rect, text, digest in sorted(heap, reverse=True):
                if cancelled():
                    raise SearchCancelled()
                if path not in checked:
                    try:
                        checked[path] = fingerprint(path)
                    except OSError:
                        checked[path] = None
                if checked[path] != digest:
                    continue
                results.append(dict(score=score, path=path, page=page, rect=json.loads(rect),
                                    text=text, digest=digest))
                if len(results) == limit:
                    break
            return results
        finally:
            connection.close()
