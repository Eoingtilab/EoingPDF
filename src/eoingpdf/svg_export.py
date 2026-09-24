"""Page SVG archive with embedded images and outlined text."""
from .localization import tr
import zipfile
from xml.etree import ElementTree
from .core import Cancelled


def export(document, target, cancelled=lambda: False, progress=lambda value: None):
    if len(document) > 10000:
        raise ValueError(tr('SVG 내보내기는 한 번에 10,000페이지까지 지원합니다. 문서를 나누어 주세요.'))
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    document.bake(annots=True, widgets=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            svg = page.get_svg_image(text_as_path=True)
            root = ElementTree.fromstring(svg)
            if root.tag != '{http://www.w3.org/2000/svg}svg':
                raise ValueError(tr('{v0}페이지의 SVG 검증에 실패했습니다.', v0=index + 1))
            archive.writestr(f'page-{index + 1:05d}.svg', svg.encode('utf-8'))
            progress(int((index + 1) / len(document) * 90))
    return len(document)
