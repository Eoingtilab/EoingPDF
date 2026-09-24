import io
import sys
import zipfile
from pathlib import Path
import ezdxf
import pymupdf as pdf
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_dxf_exact_bezier_and_display_units(tmp_path, rotation):
    source, target = tmp_path/'source.pdf', tmp_path/'paths.zip'
    with pdf.open() as document:
        page = document.new_page(width=500, height=400)
        page.draw_line((40, 50), (200, 100), color=(1, 0, 0))
        shape = page.new_shape()
        shape.draw_bezier((40, 140), (120, 220), (210, 80), (280, 160))
        shape.finish(color=(0, 0, 1), closePath=False)
        shape.commit()
        page.draw_rect(pdf.Rect(100, 250, 200, 300))
        page.set_cropbox(pdf.Rect(20, 20, 460, 360))
        page.set_rotation(rotation)
        document.new_page()
        document.save(source)
    original = source.read_bytes()
    assert transform(source, target, 'dxf') == 3
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        drawing = ezdxf.read(io.StringIO(archive.read('page-00001.dxf').decode('utf-8')))
        assert not drawing.audit().has_errors
        assert drawing.units == ezdxf.units.MM
        assert len(ezdxf.read(io.StringIO(archive.read('page-00002.dxf').decode('utf-8'))).modelspace()) == 0
    with pdf.open(source) as document:
        page = document[0]
        def point(value):
            value = pdf.Point(value) * page.rotation_matrix
            return (value.x * 25.4/72, (page.rect.height-value.y) * 25.4/72, 0)
        paths = page.get_drawings()
        line = drawing.modelspace().query('LINE')[0]
        original_line = next(item for path in paths for item in path['items'] if item[0]=='l')
        assert tuple(line.dxf.start) == pytest.approx(point(original_line[1]))
        assert tuple(line.dxf.end) == pytest.approx(point(original_line[2]))
        spline = drawing.modelspace().query('SPLINE')[0]
        curve = next(item for path in paths for item in path['items'] if item[0]=='c')
        controls = [point(value) for value in curve[1:5]]
        for actual, expected in zip(spline.control_points, controls):
            assert tuple(actual) == pytest.approx(expected)
        for t in (.1, .3, .7, .9):
            weights = ((1-t)**3, 3*t*(1-t)**2, 3*t*t*(1-t), t**3)
            expected = tuple(sum(weights[i]*controls[i][axis] for i in range(4)) for axis in range(3))
            assert tuple(spline.construction_tool().point(t)) == pytest.approx(expected)
        assert drawing.modelspace().query('LWPOLYLINE')[0].closed
    assert source.read_bytes() == original


def test_cancelled_dxf_does_not_publish(tmp_path):
    source, target = tmp_path/'source.pdf', tmp_path/'paths.zip'
    with pdf.open() as doc:
        doc.new_page().draw_line((20,20),(100,100))
        doc.save(source)
    with pytest.raises(Cancelled):
        transform(source,target,'dxf',cancelled=lambda:True)
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))
