"""Regression test ensuring fit-width PDF rendering never oscillates near scrollbar thresholds."""
import sys
from pathlib import Path

import pymupdf as pdf
import pytest
from PySide6.QtTest import QTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.viewer import PdfViewer


@pytest.mark.parametrize('size', [
    (595, 842),
    (595, 820),
    (595, 810),
    (500, 700),
    (500, 690),
    (612, 792),
])
def test_viewer_fit_width_does_not_oscillate_on_boundary_aspect_ratios(tmp_path, monkeypatch, size):
    path = tmp_path / f'{size[0]}x{size[1]}.pdf'
    with pdf.open() as document:
        document.new_page(width=size[0], height=size[1]).insert_text((48, 48), 'Boundary aspect test')
        document.save(path)
    monkeypatch.setattr('eoingpdf.sniffer_ui.MicroSniffer.start', lambda *args, **kwargs: None)
    viewer = PdfViewer(path)
    renders = []
    original_render = viewer.render

    def tracked_render(*args, **kwargs):
        renders.append((viewer.scroll.viewport().width(), viewer.canvas.width(), viewer.canvas.height()))
        return original_render(*args, **kwargs)

    viewer.render = tracked_render
    viewer.fit_timer.timeout.disconnect()
    viewer.fit_timer.timeout.connect(viewer.render)
    try:
        viewer.show()
        QTest.qWait(350)
        assert len(renders) <= 3, f'Render oscillated for {size}: {renders}'
    finally:
        viewer.close()
