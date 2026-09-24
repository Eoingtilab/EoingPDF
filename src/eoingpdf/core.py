"""Offline PDF operations. Never modify an input or overwrite an output."""
from .localization import tr
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
import zipfile

import pymupdf as pdf

IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}


class Cancelled(Exception):
    pass


def pages_from_text(text, count):
    if not text.strip():
        return list(range(count))
    result = []
    try:
        for token in text.replace(' ', '').split(','):
            if '-' in token:
                start, stop = (count if part.lower() == 'end' else int(part) for part in token.split('-'))
                if not (1 <= start <= count and 1 <= stop <= count):
                    raise ValueError
                if len(result) + abs(stop - start) + 1 > 100000:
                    raise ValueError
                step = 1 if stop >= start else -1
                result.extend(range(start - 1, stop - 1 + step, step))
            else:
                page = int(token)
                if not 1 <= page <= count:
                    raise ValueError
                result.append(page - 1)
            if len(result) > 100000:
                raise ValueError
    except (ValueError, OverflowError):
        raise ValueError(tr('페이지는 1-3, 5, 8-6처럼 입력해 주세요.')) from None
    if not result or any(p < 0 or p >= count for p in result):
        raise ValueError(tr('페이지는 1부터 {v0} 사이로 입력해 주세요.', v0=count))
    return result


@contextmanager
def open_pdf(path, password=''):
    with pdf.open(path) as doc:
        if not doc.is_pdf:
            raise ValueError(tr('PDF 파일을 선택해 주세요.'))
        if doc.needs_pass and not doc.authenticate(password):
            raise ValueError(tr('PDF 암호가 필요하거나 암호가 맞지 않습니다. 암호 도구에서 해제한 사본을 만들 수 있습니다.'))
        if not doc.page_count:
            raise ValueError(tr('페이지가 없는 PDF입니다.'))
        yield doc


@dataclass(frozen=True)
class Request:
    tool: str
    files: tuple
    folder: str
    pages: str = ''
    rotation: int = 90


def run(request, progress=lambda value, message: None, cancelled=lambda: False):
    paths = [Path(p).resolve() for p in request.files]
    if not paths:
        raise ValueError(tr('파일을 먼저 추가해 주세요.'))
    if request.tool not in {'merge', 'extract', 'rotate', 'optimize', 'images', 'png', 'text', 'number'}:
        raise ValueError(tr('지원하지 않는 작업입니다.'))
    if request.tool not in {'merge', 'images'} and len(paths) != 1:
        raise ValueError(tr('이 도구에서는 파일을 하나만 선택해 주세요.'))
    for path in paths:
        if not path.is_file():
            raise ValueError(tr('파일을 찾을 수 없습니다: {v0}', v0=path.name))
        if request.tool == 'images':
            if path.suffix.lower() not in IMAGES:
                raise ValueError(tr('JPG, PNG, WEBP, BMP, TIFF 이미지를 선택해 주세요.'))
        elif path.suffix.lower() != '.pdf':
            raise ValueError(tr('PDF 파일을 선택해 주세요.'))
    folder = Path(request.folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    suffix = '.zip' if request.tool == 'png' else '.txt' if request.tool == 'text' else '.pdf'
    names = dict(merge=tr('합친문서'), extract=tr('페이지정리'), rotate=tr('회전'), optimize=tr('최적화'), images=tr('이미지문서'), png=tr('페이지이미지'), text=tr('텍스트'), number=tr('페이지번호'))
    stem = f'{paths[0].stem}_{names[request.tool]}'
    handle, scratch = tempfile.mkstemp(prefix='.eoing-', suffix=suffix, dir=folder)
    os.close(handle)
    scratch = Path(scratch)

    def tick(index, total, message):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다. 원본은 그대로입니다.'))
        progress(int(index / max(total, 1) * 95), message)

    try:
        tick(0, 1, tr('문서를 준비하고 있습니다'))
        if request.tool in {'merge', 'images'}:
            with pdf.open() as out:
                contents = []
                for index, path in enumerate(paths):
                    tick(index, len(paths), f'{index + 1}/{len(paths)} · {path.name}')
                    contents.append([1, path.stem, len(out) + 1])
                    if request.tool == 'merge':
                        with open_pdf(path) as doc:
                            out.insert_pdf(doc)
                    else:
                        with pdf.open(path) as image_doc:
                            with pdf.open('pdf', image_doc.convert_to_pdf()) as converted:
                                out.insert_pdf(converted)
                out.set_toc(contents)
                out.save(scratch, garbage=4, deflate=True)
        else:
            with open_pdf(paths[0]) as doc:
                selected = pages_from_text(request.pages, doc.page_count)
                if request.tool == 'extract':
                    with pdf.open() as out:
                        for i, p in enumerate(selected):
                            tick(i, len(selected), tr('{v0}페이지를 담고 있습니다', v0=p + 1))
                            out.insert_pdf(doc, from_page=p, to_page=p)
                        out.save(scratch, garbage=4, deflate=True)
                elif request.tool == 'png':
                    with zipfile.ZipFile(scratch, 'w', zipfile.ZIP_DEFLATED) as archive:
                        for i, p in enumerate(selected):
                            tick(i, len(selected), tr('{v0}페이지를 이미지로 바꾸고 있습니다', v0=p + 1))
                            page = doc[p]
                            scale = min(2, 4000 / max(page.rect.width, page.rect.height))
                            pixmap = page.get_pixmap(matrix=pdf.Matrix(scale, scale), alpha=False)
                            archive.writestr(f'{i + 1:04d}_page-{p + 1}.png', pixmap.tobytes('png'))
                elif request.tool == 'text':
                    has_text = False
                    with scratch.open('w', encoding='utf-8-sig') as stream:
                        for i, p in enumerate(selected):
                            tick(i, len(selected), tr('{v0}페이지에서 글자를 읽고 있습니다', v0=p + 1))
                            from .ocr import page_text
                            text, used_ocr = page_text(doc[p], cancelled)
                            has_text |= bool(text.strip())
                            stream.write(tr('--- {v0}페이지{v1} ---\n{v2}\n', v0=p + 1, v1=" (OCR)" if used_ocr else "", v2=text))
                    if not has_text:
                        raise ValueError(tr('추출할 글자가 없습니다. 이미지가 선명한지 확인해 주세요.'))
                else:
                    if request.tool == 'rotate':
                        if request.rotation not in (90, 180, 270):
                            raise ValueError(tr('회전 각도를 확인해 주세요.'))
                        for i, p in enumerate(dict.fromkeys(selected)):
                            tick(i, len(selected), tr('{v0}페이지를 회전하고 있습니다', v0=p + 1))
                            doc[p].set_rotation((doc[p].rotation + request.rotation) % 360)
                    elif request.tool == 'number':
                        for i, p in enumerate(dict.fromkeys(selected)):
                            tick(i, len(selected), tr('{v0}페이지에 번호를 넣고 있습니다', v0=p + 1))
                            page = doc[p]
                            old_rotation = page.rotation
                            page.set_rotation(0)
                            rect = page.rect
                            page.insert_textbox(pdf.Rect(8, rect.height - 27, rect.width - 8, rect.height - 8), f'{p + 1} / {doc.page_count}', fontsize=9, align=1, color=(0.4, 0.43, 0.5))
                            page.set_rotation(old_rotation)
                    tick(0, 1, tr('새 PDF를 저장하고 있습니다'))
                    doc.save(scratch, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True)
        tick(1, 1, tr('결과를 확인하고 있습니다'))
        if suffix == '.pdf':
            with open_pdf(scratch) as output_doc:
                if output_doc.page_count < 1:
                    raise ValueError(tr('결과에 페이지가 없습니다.'))
        # Exclusive creation makes collisions safe, including the source file itself.
        for index in range(10000):
            target = folder / f'{stem}{f" ({index})" if index else ""}{suffix}'
            try:
                output = target.open('xb')
            except FileExistsError:
                continue
            try:
                with output, scratch.open('rb') as source:
                    import shutil
                    shutil.copyfileobj(source, output)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            break
        else:
            raise ValueError(tr('같은 이름의 파일이 너무 많습니다. 다른 폴더를 선택해 주세요.'))
        progress(100, tr('완료했습니다'))
        return target
    finally:
        scratch.unlink(missing_ok=True)
