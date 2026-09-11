from pathlib import Path
import shutil
import tempfile
from .convert import to_pdf, SUPPORTED
from .core import Request, run, Cancelled
from .summary import summarize


def publish(source, folder, name):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(name)
    for index in range(10000):
        target = folder / f'{name.stem}{f" ({index})" if index else ""}{name.suffix}'
        try:
            output = target.open('xb')
        except FileExistsError:
            continue
        try:
            with output, Path(source).open('rb') as stream:
                shutil.copyfileobj(stream, output)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
    raise ValueError('다른 저장 폴더를 선택해 주세요.')


def execute(action, files, folder=None, progress=lambda value, message: None, cancelled=lambda: False):
    paths = [Path(p).resolve() for p in files]
    if action not in {'merge', 'convert', 'summary'} or not paths:
        raise ValueError('작업과 파일을 확인해 주세요.')
    if any(not p.is_file() or p.suffix.lower() not in SUPPORTED for p in paths):
        raise ValueError('지원하지 않거나 찾을 수 없는 파일이 포함되어 있습니다.')
    outputs, errors = [], []
    with tempfile.TemporaryDirectory(prefix='eoingpdf-') as temporary:
        temp = Path(temporary)
        converted = []
        for index, path in enumerate(paths):
            if cancelled():
                break
            progress(int(index / len(paths) * 80), f'{index + 1}/{len(paths)} · {path.name}')
            try:
                if path.suffix.lower() == '.pdf':
                    from .core import open_pdf
                    with open_pdf(path):
                        pass
                    result = path
                else:
                    result = temp / f'{index}.pdf'
                    to_pdf(path, result, cancelled)
                converted.append(result)
                if action == 'convert':
                    outputs.append(publish(result, folder or path.parent, f'{path.stem}_변환.pdf'))
                elif action == 'summary':
                    text = summarize(result, cancelled)
                    draft = temp / f'{index}.txt'
                    draft.write_text(f'어잉PDF · 핵심문장 요약\n출처: {path.name}\n\n{text}', encoding='utf-8-sig')
                    outputs.append(publish(draft, folder or path.parent, f'{path.stem}_요약.txt'))
            except Cancelled:
                break
            except Exception as error:
                errors.append(f'{path.name}: {error}')
                if action == 'merge':
                    return {'outputs': [], 'errors': errors, 'cancelled': False}
        was_cancelled = cancelled()
        if action == 'merge' and not was_cancelled:
            try:
                merged = run(Request('merge', tuple(str(p) for p in converted), str(temp)), lambda value, message: progress(80 + int(value * .2), message), cancelled)
                outputs.append(publish(merged, folder or paths[0].parent, f'{paths[0].stem}_병합.pdf'))
            except Cancelled:
                was_cancelled = True
        return {'outputs': [str(p) for p in outputs], 'errors': errors, 'cancelled': was_cancelled}
