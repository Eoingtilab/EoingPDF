import re
import struct
import sys
from pathlib import Path
from unittest.mock import patch
import pymupdf as pdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.clipboard_tools import page_dib, table_payload, html_clipboard, selection_rect, extract_table, copy_table


def test_unicode_html_byte_offsets_and_escaping():
    tsv, packet = table_payload([['이름', '금액'], ['<홍&길동>', '1,000'], [None, '두\n줄']])
    offsets = {key.decode(): int(value) for key, value in re.findall(rb'(StartHTML|EndHTML|StartFragment|EndFragment):(\d+)', packet)}
    assert offsets['EndHTML'] == len(packet)
    fragment = packet[offsets['StartFragment']:offsets['EndFragment']].decode('utf-8')
    assert fragment.startswith('<table>') and fragment.endswith('</table>')
    assert '&lt;홍&amp;길동&gt;' in fragment
    assert '두<br>줄' in fragment
    assert '이름\t금액\r\n' in tsv
    assert packet[offsets['StartHTML']:].startswith(b'<html>')


def test_spreadsheet_formula_is_copied_as_text():
    tsv, _ = table_payload([['=HYPERLINK("bad")', '-10', '+23', '@SUM(A1)']])
    assert "'=HYPERLINK" in tsv
    assert '\t-10\t+23\t' in tsv
    assert "'@SUM" in tsv


def test_dib_contains_300dpi_24bit_pixels():
    with pdf.open() as doc:
        page = doc.new_page(width=72, height=144)
        data = page_dib(page)
    size, width, height, planes, bits = struct.unpack_from('<IiiHH', data)
    assert (size, width, height, planes, bits) == (40, 300, 600, 1, 24)
    xppm, yppm = struct.unpack_from('<ii', data, 24)
    assert abs(xppm - 11811) <= 1 and abs(yppm - 11811) <= 1
    assert len(data) == 40 + 300 * 3 * 600


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_selection_and_table_on_rotated_page(rotation):
    with pdf.open() as doc:
        page = doc.new_page(width=400, height=300)
        for x in (50, 150, 250):
            page.draw_line((x, 50), (x, 150))
        for y in (50, 100, 150):
            page.draw_line((50, y), (250, y))
        for x, y, text in [(60, 80, 'A'), (160, 80, 'B'), (60, 130, '1'), (160, 130, '2')]:
            page.insert_text((x, y), text)
        page.set_rotation(rotation)
        original = pdf.Rect(40, 40, 260, 160)
        display = original * page.rotation_matrix
        screen = tuple(value * 2 for value in display)
        clip = selection_rect(page, screen, (page.rect.width * 2, page.rect.height * 2))
        assert all(abs(a - b) < .01 for a, b in zip(clip, original))
        assert extract_table(page, clip) == [['A', 'B'], ['1', '2']]
        assert page.rotation == rotation


def test_table_publishes_both_formats_without_touching_real_clipboard():
    with patch('eoingpdf.clipboard_tools.publish') as publish, patch('win32clipboard.RegisterClipboardFormat', return_value=49300):
        copy_table([['A', 'B']], 123)
    formats, owner = publish.call_args.args
    assert owner == 123
    assert len(formats) == 2 and formats[0][0] == 13 and formats[1][0] == 49300
    assert formats[0][1] == 'A\tB\r\n'
