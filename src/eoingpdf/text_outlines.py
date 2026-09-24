"""Create a vector PDF whose visible text has no font dependency."""
from .localization import tr
import pymupdf as pdf
from .core import Cancelled


def export(document, target, cancelled=lambda: False, progress=lambda value: None):
    if not len(document):
        raise ValueError(tr('변환할 페이지가 없습니다.'))
    document.bake(annots=True, widgets=True)
    with pdf.open() as output:
        for index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            svg = page.get_svg_image(text_as_path=True).encode('utf-8')
            with pdf.open(stream=svg, filetype='svg') as vector:
                converted = vector.convert_to_pdf()
            with pdf.open(stream=converted, filetype='pdf') as single:
                if len(single) != 1 or single[0].get_fonts(full=True) or single[0].get_text().strip():
                    raise ValueError(tr('{v0}페이지에 글꼴 의존성이 남아 있습니다.', v0=index + 1))
                if abs(single[0].rect.width - page.rect.width) > .1 or abs(single[0].rect.height - page.rect.height) > .1:
                    raise ValueError(tr('{v0}페이지의 크기가 달라졌습니다.', v0=index + 1))
                output.insert_pdf(single)
            progress(int((index + 1) / len(document) * 90))
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        output.set_metadata(document.metadata)
        toc = document.get_toc()
        if toc:
            output.set_toc(toc)
        output.save(target, garbage=4, deflate=True)
    return len(document)
