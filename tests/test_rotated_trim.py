import sys
from pathlib import Path
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('cropped', [False, True])
def test_trim_keeps_rotation_and_content(tmp_path, rotation, cropped):
    source, target = tmp_path / 'source.pdf', tmp_path / 'result.pdf'
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((180, 300), 'Keep rotated text')
        page.draw_rect(pdf.Rect(150, 330, 400, 450), fill=(0, 0, 1))
        annotation = page.add_rect_annot(pdf.Rect(160, 470, 410, 520))
        annotation.set_colors(stroke=(1, 0, 0))
        annotation.update()
        if cropped:
            page.set_cropbox(pdf.Rect(80, 100, 520, 650))
        page.set_rotation(rotation)
        expected_text = page.get_text().strip()
        expected_direction = page.get_text('dict')['blocks'][0]['lines'][0]['dir']
        document.save(source)
    before = source.read_bytes()
    assert transform(source, target, 'trim') == 1
    with pdf.open(source) as original, pdf.open(target) as result:
        page = result[0]
        assert page.rotation == rotation
        assert page.rect.width < original[0].rect.width
        assert page.rect.height < original[0].rect.height
        assert page.get_text().strip() == expected_text
        assert page.get_text('dict')['blocks'][0]['lines'][0]['dir'] == expected_direction
        assert any(item.get('fill') == (0, 0, 1) for item in page.get_drawings())
        annotation = next(page.annots())
        unrotated = pdf.Rect(0, 0, page.cropbox.width, page.cropbox.height)
        assert unrotated.contains(annotation.rect)
        pixmap = page.get_pixmap(colorspace=pdf.csRGB)
        pixels = pixmap.samples
        assert any(pixels[i:i+3] == b'\x00\x00\xff' for i in range(0, len(pixels), 3))
    assert source.read_bytes() == before


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_trim_preserves_link_outside_text(tmp_path, rotation):
    source, target = tmp_path / 'linked.pdf', tmp_path / 'result.pdf'
    with pdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((200, 350), 'Small text')
        page.insert_link({'kind': pdf.LINK_URI, 'from': pdf.Rect(80, 100, 160, 150),
                          'uri': 'https://example.org'})
        page.set_rotation(rotation)
        document.save(source)
    transform(source, target, 'trim')
    with pdf.open(target) as document:
        page = document[0]
        links = page.get_links()
        assert len(links) == 1 and links[0]['uri'] == 'https://example.org'
        assert page.rect.contains(links[0]['from'])
        assert 'Small text' in page.get_text()
