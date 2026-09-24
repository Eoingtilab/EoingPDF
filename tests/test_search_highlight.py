import sys
from pathlib import Path
import pymupdf as pdf
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.viewer import PdfViewer
from eoingpdf.semantic_search import fingerprint


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_search_page_highlight_rotation_crop_zoom_and_original_preserved(tmp_path, rotation):
    source = tmp_path / 'result.pdf'
    with pdf.open() as doc:
        doc.new_page()
        page = doc.new_page(width=600, height=1200)
        page.insert_text((90, 900), 'Search result content', fontsize=18)
        page.set_cropbox(pdf.Rect(40, 40, 560, 1100))
        page.set_rotation(rotation)
        doc.save(source)
    original = source.read_bytes()
    with pdf.open(source) as doc:
        rect = list(doc[1].get_text('blocks')[0][:4])
        visible = pdf.Rect(rect) * doc[1].rotation_matrix
        expected = (visible.x0 / doc[1].rect.width, visible.y0 / doc[1].rect.height)
    window = PdfViewer(source)
    window.resize(950, 700)
    window.show()
    try:
        QTest.qWait(50)
        window.show_search_result(dict(path=str(source), page=1, rect=rect, digest=fingerprint(source)))
        QTest.qWait(50)
        assert window.page.value() == 2
        area = window.canvas.search_highlight
        assert area.x() == pytest.approx(expected[0])
        assert area.y() == pytest.approx(expected[1])
        image = window.canvas.grab().toImage()
        x = round(area.left() * image.width()) + 3
        y = round(area.top() * image.height()) + 3
        color = image.pixelColor(x, y)
        assert color.red() > color.blue() + 15  # Actual amber overlay pixels.
        point = window.canvas.mapTo(window.scroll.viewport(), QPoint(
            round(area.center().x() * window.canvas.width()), round(area.center().y() * window.canvas.height())))
        assert window.scroll.viewport().rect().contains(point)
        window.zoom.setCurrentIndex(2)
        assert window.canvas.search_highlight == area
        window.page.setValue(1)
        assert window.canvas.search_highlight is None
        assert source.read_bytes() == original
    finally:
        window.close()


def test_stale_search_result_is_not_highlighted(tmp_path):
    source = tmp_path / 'result.pdf'
    with pdf.open() as doc:
        doc.new_page()
        doc.save(source)
    window = PdfViewer(source)
    try:
        with pytest.raises(ValueError, match='변경'):
            window.show_search_result(dict(path=str(source), page=0, rect=[10, 10, 20, 20], digest='old'))
        assert window.search_hit is None
    finally:
        window.close()
