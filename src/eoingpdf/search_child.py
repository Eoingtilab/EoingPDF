"""One search/index job per process, with local-only stdin and cancellation."""
from .localization import tr
import json
import os
from pathlib import Path
import sys


def child_main():
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    from .semantic_search import LocalEmbedder, PdfSearchIndex, SearchCancelled
    def send(payload):
        print(json.dumps(payload, ensure_ascii=True), flush=True)
    try:
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            raise ValueError(tr('검색 요청이 너무 큽니다.'))
        options = json.loads(payload)
        from .localization import configure_language
        configure_language(options.get('locale'))
        if not options.get('model_folder'):
            from .distribution import resource_root
            options['model_folder'] = str(resource_root() / 'assets/search')
        mode = options['mode']
        if mode not in ('prepare', 'complete', 'search'):
            raise ValueError(tr('지원하지 않는 검색 작업입니다.'))
        cancel_path = Path(options['cancel_path'])
        if cancel_path.exists():
            raise SearchCancelled()
        progress = lambda done, total: send(dict(type='progress', value=int(done / max(1, total) * 100)))
        if mode == 'prepare':
            from .search_staging import prepare
            result = prepare(options['model_folder'], options['folder'], options['database'],
                options['staged'], cancelled=cancel_path.exists, progress=progress, use_ocr=options.get('use_ocr') is True)
            result['error_count'] = len(result['errors'])
            result['errors'] = result['errors'][:20]
            for error in result['errors']:
                error['message'] = error['message'][:300]
        elif mode == 'complete':
            from .search_staging import complete
            result = complete(options['model_folder'], options['database'], options['staged'],
                cancelled=cancel_path.exists, progress=progress)
        else:
            index = PdfSearchIndex(options['database'], LocalEmbedder(options['model_folder']))
            result = index.search(options['query'], limit=10, cancelled=cancel_path.exists)
            for entry in result:
                entry['text'] = entry['text'][:300]
        if cancel_path.exists():
            raise SearchCancelled()
        message = json.dumps(result, ensure_ascii=False)
        if len(json.dumps(message, ensure_ascii=True).encode('utf-8')) > 100000:
            raise ValueError(tr('검색 결과가 너무 큽니다. 더 작은 폴더로 다시 시도해 주세요.'))
        send(dict(type='result', success=True, message=message))
    except SearchCancelled:
        send(dict(type='result', success=False, message=tr('검색 작업을 취소했습니다.')))
    except (OSError, ValueError, KeyError, TypeError) as error:
        send(dict(type='result', success=False, message=str(error)[:500]))
    except Exception:
        send(dict(type='result', success=False, message=tr('검색 모델과 색인 파일을 확인해 주세요.')))
    return 0
