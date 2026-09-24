"""Range, fixed-size and top-level bookmark splitting into one atomic ZIP."""
from .localization import tr
import re
import zipfile
import pymupdf as pdf
from .core import pages_from_text, Cancelled


def plan(document, mode, ranges='', group_size=1):
    count = len(document)
    if mode == 'split_ranges':
        tokens = [token.strip() for token in ranges.split(',')]
        if not ranges.strip() or any(not token for token in tokens):
            raise ValueError(tr('분할 범위를 1-3, 5, 8-end처럼 입력해 주세요.'))
        groups = [(token, pages_from_text(token, count)) for token in tokens]
    elif mode == 'split_groups':
        if type(group_size) is not int or not 1 <= group_size <= 100000:
            raise ValueError(tr('묶음 크기는 1부터 100000 사이의 정수여야 합니다.'))
        groups = [(f'{start + 1}-{min(start + group_size, count)}', list(range(start, min(start + group_size, count))))
                  for start in range(0, count, group_size)]
    elif mode == 'split_toc':
        entries = [(title, page - 1) for level, title, page in document.get_toc()
                   if level == 1 and 1 <= page <= count]
        if not entries:
            raise ValueError(tr('분할할 최상위 목차가 없습니다. 범위 또는 페이지 수로 분할해 주세요.'))
        starts = {}
        for title, page in entries:
            starts.setdefault(page, title)
        starts.setdefault(0, tr('앞부분'))
        ordered = sorted(starts)
        groups = [(starts[start], list(range(start, ordered[index + 1] if index + 1 < len(ordered) else count)))
                  for index, start in enumerate(ordered)]
    else:
        raise ValueError(tr('지원하지 않는 분할 방식입니다.'))
    if len(groups) > 10000 or sum(len(pages) for _, pages in groups) > 100000:
        raise ValueError(tr('한 번에 최대 1만 파일, 총 10만 페이지까지 분할할 수 있습니다.'))
    return groups


def write_archive(document, target, mode, ranges='', group_size=1, cancelled=lambda: False, progress=lambda value: None):
    groups = plan(document, mode, ranges, group_size)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for index, (title, pages) in enumerate(groups):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:70] or tr('문서')
            filename = f'{index + 1:04d}_{safe}.pdf'
            with pdf.open() as output:
                for page in pages:
                    if cancelled():
                        raise Cancelled(tr('작업을 취소했습니다.'))
                    output.insert_pdf(document, from_page=page, to_page=page)
                output.set_metadata(document.metadata)
                archive.writestr(filename, output.tobytes(garbage=4, deflate=True))
            progress(int((index + 1) / len(groups) * 90))
    return len(groups)
