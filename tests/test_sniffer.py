import sys
from pathlib import Path
import pymupdf as pdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.sniffer import inspect_pdf


def test_first_page_only_and_slide_detection(tmp_path):
    path = tmp_path / 'slides.pdf'
    with pdf.open() as doc:
        for index in range(10):
            page = doc.new_page(width=960, height=540)
            page.insert_text((40, 60), 'Heading' if index == 0 else 'NEXT PAGE')
        doc.set_metadata({'author': 'Synthetic Author'})
        doc.save(path)
    report = inspect_pdf(path, budget_ms=100)
    codes = {finding['code'] for finding in report['diagnostics']}
    assert {'D-03', 'D-04', 'D-09'} <= codes
    assert report['pages_scanned'] == 1
    assert report['page_count'] == 10
    assert report['suggested_name'] == 'Heading.pdf'
    assert report['elapsed_ms'] > 0


def test_budget_is_reported_not_silently_claimed(tmp_path):
    path = tmp_path / 'simple.pdf'
    with pdf.open() as doc:
        doc.new_page()
        doc.save(path)
    report = inspect_pdf(path, budget_ms=0)
    assert report['partial']
    assert not report['within_budget']
    assert report['pages_scanned'] == 0


def test_dark_background_requires_print_trigger(tmp_path):
    path = tmp_path / 'dark.pdf'
    with pdf.open() as doc:
        page = doc.new_page()
        page.draw_rect(page.rect, fill=(0, 0, 0))
        doc.save(path)
    regular = inspect_pdf(path, budget_ms=100)
    printing = inspect_pdf(path, budget_ms=100, trigger='print')
    assert 'D-05' not in {entry['code'] for entry in regular['diagnostics']}
    assert 'D-05' in {entry['code'] for entry in printing['diagnostics']}
