import io
import sys
from pathlib import Path

import pymupdf as pdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform


def test_dark_print_copy_keeps_photos_color_art_and_light_pages(tmp_path):
    source, target = tmp_path / 'mixed.pdf', tmp_path / 'print.pdf'
    image = io.BytesIO()
    Image.new('RGB', (40, 40), (10, 100, 210)).save(image, format='PNG')
    with pdf.open() as document:
        dark = document.new_page(width=300, height=200)
        dark.draw_rect(dark.rect, color=None, fill=(.08, .08, .08))
        dark.insert_text((20, 40), 'WHITE TITLE', color=(1, 1, 1), fontsize=20)
        dark.draw_rect(pdf.Rect(220, 150, 250, 175), color=None, fill=(1, 0, 0))
        dark.insert_image(pdf.Rect(200, 50, 270, 120), stream=image.getvalue())
        light = document.new_page(width=300, height=200)
        light.draw_rect(pdf.Rect(20, 20, 100, 50), color=None, fill=(0, 0, 0))
        document.save(source)
    original = source.read_bytes()
    transform(source, target, 'print_light')
    with pdf.open(target) as document:
        assert len(document) == 2
        first = document[0].get_pixmap()
        assert first.pixel(10, 100) == (255, 255, 255)
        assert first.pixel(230, 160) == (255, 0, 0)
        photo = first.pixel(230, 80)
        assert all(abs(a - b) <= 1 for a, b in zip(photo, (10, 100, 210)))
        # White native title is rendered as dark ink, not lost on white paper.
        title = document[0].get_pixmap(clip=pdf.Rect(20, 20, 150, 44))
        assert min(title.samples) == 0
        second = document[1].get_pixmap()
        assert second.pixel(10, 100) == (255, 255, 255)
        assert second.pixel(40, 30) == (0, 0, 0)
    assert source.read_bytes() == original


def test_print_menu_starts_diagnostics_and_routes_tools(tmp_path, monkeypatch):
    from eoingpdf.viewer import PdfViewer
    source = tmp_path / 'source.pdf'
    with pdf.open() as document:
        document.new_page()
        document.save(source)
    viewer = PdfViewer(source)
    calls, diagnostics = [], []
    monkeypatch.setattr(viewer, 'diagnostic_action', calls.append)
    monkeypatch.setattr(viewer.sniffer, 'start', lambda path, trigger='open': diagnostics.append((path, trigger)))
    try:
        menu = viewer.print_button.menu()
        menu.aboutToShow.emit()
        assert diagnostics == [(source, 'print')]
        for action in menu.actions():
            action.trigger()
        assert calls == ['print_light', 'four_up', 'booklet']
    finally:
        viewer.close()
