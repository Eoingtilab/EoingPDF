"""Sequential PDF extraction and ONNX embedding with atomic index publication."""
from .localization import tr
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager, closing
from .semantic_search import ModelFiles, LocalEmbedder, PdfSearchIndex, SearchCancelled, fingerprint


@contextmanager
def publication_lock(database):
    import msvcrt
    # Keep the lock file: deleting it after unlock would allow separate lock inodes.
    with Path(str(database) + '.lock').open('a+b') as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b'\0'); stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise ValueError(tr('다른 검색 작업이 색인을 저장하고 있습니다.')) from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def delete_index(database, cache_folder):
    """Delete exactly one generated cache DB without following redirected paths."""
    import re
    database, cache_folder = Path(database), Path(cache_folder).resolve()
    if not re.fullmatch(r'[0-9a-f]{64}\.sqlite3', database.name):
        raise ValueError(tr('검색 색인 파일 이름이 올바르지 않습니다.'))
    if database.is_symlink() or database.resolve().parent != cache_folder:
        raise ValueError(tr('검색 저장 폴더 밖의 파일은 삭제할 수 없습니다.'))
    if not database.exists():
        return
    with publication_lock(database):
        database.unlink(missing_ok=True)


def prepare(model_folder, folder, database, staged, cancelled=lambda: False, progress=lambda done, total: None, *, use_ocr=False):
    database, staged = Path(database).resolve(), Path(staged).resolve()
    if database == staged or staged.exists():
        raise ValueError(tr('별도의 새 임시 색인 파일이 필요합니다.'))
    staged.parent.mkdir(parents=True, exist_ok=True)
    if cancelled():
        raise SearchCancelled()
    baseline = fingerprint(database) if database.exists() else 'absent'
    if database.exists():
        source = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        destination = sqlite3.connect(staged)
        try:
            def tick(status, remaining, total):
                if cancelled():
                    raise SearchCancelled()
            source.backup(destination, pages=128, progress=tick)
        finally:
            destination.close()
            source.close()
    # ModelFiles verifies assets but imports neither NumPy nor ONNX Runtime.
    index = PdfSearchIndex(staged, ModelFiles(model_folder))
    result = index.build(folder, cancelled=cancelled, progress=progress, defer_embeddings=True, use_ocr=use_ocr)
    if (fingerprint(database) if database.exists() else 'absent') != baseline:
        raise ValueError(tr('다른 검색 작업이 색인을 변경했습니다. 다시 시도해 주세요.'))
    with closing(sqlite3.connect(staged)) as connection:
        with connection:
            connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('baseline', baseline))
    return result


def complete(model_folder, database, staged, cancelled=lambda: False, progress=lambda done, total: None):
    database, staged = Path(database).resolve(), Path(staged).resolve()
    if database == staged or not staged.is_file():
        raise ValueError(tr('준비된 임시 색인을 찾을 수 없습니다.'))
    if cancelled():
        raise SearchCancelled()
    embedder = LocalEmbedder(model_folder)
    connection = sqlite3.connect(staged, timeout=5)
    connection.execute('PRAGMA cache_size=-2048')
    try:
        with connection:
            metadata = dict(connection.execute('SELECT key,value FROM metadata'))
            if metadata.get('state') != 'pending' or metadata.get('model') != embedder.identity:
                raise ValueError(tr('임시 색인의 모델이나 작업 상태가 올바르지 않습니다.'))
            total = connection.execute('SELECT COUNT(*) FROM passages WHERE length(vector)=0').fetchone()[0]
            done = 0
            # Each fetch is bounded even when the corpus contains 100,000 passages.
            cursor = connection.execute('SELECT id,text FROM passages WHERE length(vector)=0 ORDER BY id')
            while True:
                batch = cursor.fetchmany(32)
                if not batch:
                    break
                for identifier, text in batch:
                    if cancelled():
                        raise SearchCancelled()
                    vector = embedder.encode(text).astype('<f4').tobytes()
                    connection.execute('UPDATE passages SET vector=? WHERE id=?', (vector, identifier))
                    done += 1
                progress(done, total)
            connection.execute("UPDATE metadata SET value='ready' WHERE key='state'")
    finally:
        connection.close()
    if cancelled():
        raise SearchCancelled()
    database.parent.mkdir(parents=True, exist_ok=True)
    with publication_lock(database):
        if (fingerprint(database) if database.exists() else 'absent') != metadata.get('baseline'):
            raise ValueError(tr('다른 검색 작업이 색인을 변경했습니다. 다시 시도해 주세요.'))
        os.replace(staged, database)
    return {'embedded': done}
