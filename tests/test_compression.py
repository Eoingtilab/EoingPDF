import io
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform
from eoingpdf.core import Cancelled
from eoingpdf.compression import resize_opaque_images


def test_shared_image_uses_largest_placement():
    image = Image.fromarray(np.random.default_rng(7).integers(0, 256, (800, 800, 3), dtype=np.uint8))
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    with pdf.open() as doc:
        first = doc.new_page(width=600, height=600)
        xref = first.insert_image(pdf.Rect(0, 0, 100, 100), stream=stream.getvalue())
        second = doc.new_page(width=600, height=600)
        second.insert_image(pdf.Rect(0, 0, 500, 500), xref=xref)
        resize_opaque_images(doc, 72, 80, lambda: False)
        assert doc.extract_image(xref)['width'] == 500
        assert doc[0].get_images()[0][0] == doc[1].get_images()[0][0]


def test_cancel_after_compression_trial_leaves_no_result(tmp_path):
    source, target = tmp_path / 'source.pdf', tmp_path / 'target.pdf'
    with pdf.open() as doc:
        doc.new_page()
        doc.set_metadata({'subject': 'x' * 100000})
        doc.save(source)
    state = {'cancel': False}
    def progress(value):
        state['cancel'] = True
    with pytest.raises(Cancelled):
        transform(source, target, 'target_size', target_mb=.05,
                  progress=progress, cancelled=lambda: state['cancel'])
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))


def test_target_reached_without_rasterizing_text_or_vectors(tmp_path):
    source, target = tmp_path / 'image.pdf', tmp_path / 'small.pdf'
    image = Image.fromarray(np.random.default_rng(4).integers(0, 256, (1024, 1024, 3), dtype=np.uint8))
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    with pdf.open() as doc:
        page = doc.new_page(width=600, height=700)
        page.insert_image(pdf.Rect(0, 0, 600, 600), stream=stream.getvalue())
        page.insert_text((20, 640), 'Keep this text searchable')
        page.draw_line((20, 660), (500, 660), color=(1, 0, 0))
        doc.save(source)
    original = source.read_bytes()
    transform(source, target, 'target_size', target_mb=.3)
    assert target.stat().st_size <= int(.3 * 1024 * 1024)
    assert source.read_bytes() == original
    with pdf.open(target) as result:
        assert len(result) == 1
        assert 'Keep this text searchable' in result[0].get_text()
        assert result[0].get_drawings()
    assert not list(tmp_path.glob('.eoing-*'))


def test_unattainable_target_is_not_published(tmp_path):
    source, target = tmp_path / 'metadata.pdf', tmp_path / 'impossible.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((20, 50), 'Vector-only content')
        doc.set_metadata({'subject': 'x' * 100000})
        doc.save(source)
    with pytest.raises(ValueError, match='목표 용량'):
        transform(source, target, 'target_size', target_mb=.05)
    assert not target.exists()
    assert not list(tmp_path.glob('.eoing-*'))


def test_already_small_and_cancel(tmp_path):
    source, target = tmp_path / 'small.pdf', tmp_path / 'output.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((20, 50), 'Original')
        doc.save(source)
    transform(source, target, 'target_size', target_mb=10)
    with pdf.open(target) as doc:
        assert doc[0].get_text().strip() == 'Original'
    with pytest.raises(Cancelled):
        transform(source, tmp_path / 'cancel.pdf', 'target_size', cancelled=lambda: True)
    assert not (tmp_path / 'cancel.pdf').exists()


@pytest.mark.parametrize('size', [0, -.1, float('nan'), 2001])
def test_invalid_target(tmp_path, size):
    source = tmp_path / 'source.pdf'
    with pdf.open() as doc:
        doc.new_page()
        doc.save(source)
    with pytest.raises(ValueError):
        transform(source, tmp_path / 'target.pdf', 'target_size', target_mb=size)
