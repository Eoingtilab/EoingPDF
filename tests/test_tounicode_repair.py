import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
from eoingpdf.advanced import transform

def test_damaged_tounicode_layer_is_replaced(tmp_path):
    source, target = tmp_path / 'damaged.pdf', tmp_path / 'fixed.pdf'
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=160)
        page.insert_text((30, 60), '\ufffd\ufffd\ufffd\ufffd\ufffd', fontsize=24)
        doc.save(source)
    layout = {'width': 300, 'height': 160, 'lines': [{'text': 'Recovered text', 'words': [{'text': 'Recovered', 'box': [30, 35, 70, 25]}, {'text': 'text', 'box': [105, 35, 70, 25]}]}]}
    with patch('eoingpdf.ocr.page_layout', return_value=layout):
        transform(source, target, 'searchable')
    with pdf.open(target) as doc:
        text = doc[0].get_text()
        assert 'Recovered' in text and '\ufffd' not in text
