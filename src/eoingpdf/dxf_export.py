"""Extract PDF drawing paths to per-page millimetre DXF files."""
from .localization import tr
import io
import math
import zipfile
import pymupdf as pdf
import ezdxf
from .core import Cancelled

MM = 25.4 / 72


def export(document, target, cancelled=lambda: False, progress=lambda value: None):
    if len(document) > 10000:
        raise ValueError(tr('DXF 내보내기는 한 번에 10,000페이지까지 지원합니다.'))
    total = 0
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for index, page in enumerate(document):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            drawing = ezdxf.new('R2010')
            drawing.units = ezdxf.units.MM
            space = drawing.modelspace()
            drawing.layers.new('PDF_PATHS')
            def point(value):
                value = pdf.Point(value) * page.rotation_matrix
                result = (value.x * MM, (page.rect.height - value.y) * MM, 0)
                if not all(math.isfinite(number) for number in result):
                    raise ValueError(tr('유효하지 않은 벡터 좌표입니다.'))
                return result
            for path in page.get_drawings():
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                color = path.get('color') or path.get('fill') or (0, 0, 0)
                attributes = dict(layer='PDF_PATHS', true_color=ezdxf.colors.rgb2int(tuple(
                    max(0, min(255, round(channel * 255))) for channel in color)))
                first = last = None
                for item in path['items']:
                    kind = item[0]
                    if kind == 'l':
                        start, end = point(item[1]), point(item[2])
                        space.add_line(start, end, dxfattribs=attributes)
                    elif kind == 'c':
                        control = [point(value) for value in item[1:5]]
                        space.add_open_spline(control, degree=3, knots=[0, 0, 0, 0, 1, 1, 1, 1], dxfattribs=attributes)
                        start, end = control[0], control[-1]
                    elif kind in ('re', 'qu'):
                        rect = item[1]
                        corners = (rect.tl, rect.tr, rect.br, rect.bl) if kind == 're' else (rect.ul, rect.ur, rect.lr, rect.ll)
                        vertices = [point(value) for value in corners]
                        space.add_lwpolyline([value[:2] for value in vertices], close=True, dxfattribs=attributes)
                        start = end = vertices[0]
                    else:
                        raise ValueError(tr('지원하지 않는 PDF 경로 요소입니다: {v0}', v0=kind))
                    if first is None or last != start:
                        first = start
                    last = end
                    total += 1
                    if total > 1000000:
                        raise ValueError(tr('벡터 요소가 1,000,000개를 초과합니다. 문서를 나누어 주세요.'))
                if path.get('closePath') and first is not None and last != first:
                    space.add_line(last, first, dxfattribs=attributes)
            stream = io.StringIO()
            drawing.write(stream)
            content = stream.getvalue()
            check = ezdxf.read(io.StringIO(content))
            if check.audit().has_errors:
                raise ValueError(tr('{v0}페이지의 DXF 검증에 실패했습니다.', v0=index + 1))
            archive.writestr(f'page-{index + 1:05d}.dxf', content.encode('utf-8'))
            progress(int((index + 1) / len(document) * 90))
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        archive.writestr('README.txt',
                        'PDF drawing paths in millimetres; origin is the displayed page bottom-left.\n'
                        'Cubic Bezier control points are preserved as clamped degree-3 SPLINEs.\n'
                        'This is path extraction: text, images, fill shading, dash patterns and clipping masks are not exported.\n'
                        'Paths hidden by masks may be present. Review dimensions before CAD production.\n')
    return total
