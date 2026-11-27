"""Comprehensive tests for Stirling-class extra PDF tools, QR encoder, and pipelines."""
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import numpy as np
import pymupdf as pdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import TOOLS, transform
from eoingpdf.convert import to_pdf
from eoingpdf.extra_tools import export_document, inspect_pdf_report
from eoingpdf.pipeline import DEFAULT_PIPELINES, run_pipeline
from eoingpdf.qr_code import make_qr_png
from eoingpdf.visual_diff import compare_text


def _sample_pdf(path: Path, pages: int = 2) -> Path:
    with pdf.open() as doc:
        for i in range(pages):
            page = doc.new_page(width=595, height=842)
            page.insert_text((60, 80), f'Heading Page {i + 1}', fontsize=20)
            page.insert_text((60, 120), f'Body line for page {i + 1}. SecretWordHere.', fontsize=11)
        doc.save(path)
    return path


def test_qr_code_is_decodable_by_opencv(tmp_path):
    payload = 'https://app.nal.la/eoingpdf?v=2.5.0'
    png_bytes = make_qr_png(payload)
    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    detector = cv2.QRCodeDetector()
    decoded, _, _ = detector.detectAndDecode(img)
    assert decoded == payload

    source = _sample_pdf(tmp_path / 'doc.pdf', pages=1)
    target = tmp_path / 'qr.pdf'
    assert transform(source, target, 'qr_stamp', qr_text=payload, stamp_pages='1') == 1
    with pdf.open(target) as doc:
        assert doc[0].get_images()


def test_export_all_formats(tmp_path):
    source = _sample_pdf(tmp_path / 'sample.pdf', pages=2)
    for fmt, ext in [
        ('pdf', '.pdf'),
        ('pdfa', '.pdf'),
        ('png_zip', '.zip'),
        ('jpg_zip', '.zip'),
        ('long_png', '.png'),
        ('long_jpg', '.jpg'),
        ('txt', '.txt'),
        ('md', '.md'),
        ('html', '.html'),
        ('json', '.json'),
        ('xml', '.xml'),
        ('svg', '.zip'),
        ('dxf', '.zip'),
    ]:
        out = tmp_path / f'out_{fmt}{ext}'
        export_document(source, out, fmt)
        assert out.is_file() and out.stat().st_size > 0
        if fmt == 'json':
            data = json.loads(out.read_text(encoding='utf-8'))
            assert data['page_count'] == 2
        elif fmt == 'xml':
            root = ET.parse(out).getroot()
            assert root.attrib['pageCount'] == '2'
        elif fmt == 'html':
            assert 'Heading Page 1' in out.read_text(encoding='utf-8')


def test_html_to_pdf_conversion(tmp_path):
    html_file = tmp_path / 'page.html'
    html_file.write_text('<h1>EoingPDF HTML Test</h1><p>Paragraph text here.</p>', encoding='utf-8')
    out_pdf = tmp_path / 'converted.pdf'
    to_pdf(html_file, out_pdf)
    with pdf.open(out_pdf) as doc:
        assert len(doc) >= 1
        assert 'EoingPDF HTML Test' in doc[0].get_text()


def test_page_transform_suite(tmp_path):
    source = _sample_pdf(tmp_path / 'base.pdf', pages=2)
    # Rotate, Scale, Insert Blank, Overlay, Split Size, Page Numbers, Bookmarks
    rotated = tmp_path / 'rot.pdf'
    transform(source, rotated, 'rotate', rotation=90, page_range='1')
    with pdf.open(rotated) as doc:
        assert doc[0].rotation == 90 and doc[1].rotation == 0

    scaled = tmp_path / 'letter.pdf'
    transform(source, scaled, 'scale_pages', paper_size='LETTER')
    with pdf.open(scaled) as doc:
        assert abs(doc[0].rect.width - 612) < 1 and abs(doc[0].rect.height - 792) < 1

    blanked = tmp_path / 'blanked.pdf'
    transform(source, blanked, 'insert_blank', insert_after=1, insert_count=2)
    with pdf.open(blanked) as doc:
        assert len(doc) == 4

    over = _sample_pdf(tmp_path / 'overlay_src.pdf', pages=1)
    overlaid = tmp_path / 'overlaid.pdf'
    transform(source, overlaid, 'overlay_pdf', overlay_path=str(over), overlay_foreground=False)
    assert overlaid.is_file()

    numbered = tmp_path / 'numbered.pdf'
    transform(source, numbered, 'page_numbers', number_start=10, number_position='bottom-right')
    with pdf.open(numbered) as doc:
        assert '10 / 2' in doc[0].get_text().replace('\xa0', ' ')

    # Auto-rotate check on rotated text page
    sideways = tmp_path / 'sideways.pdf'
    with pdf.open() as doc:
        p = doc.new_page(width=842, height=595)
        p.insert_text((100, 100), 'Rotated text sample line', rotate=90)
        doc.save(sideways)
    auto_rot = tmp_path / 'auto_rot.pdf'
    transform(sideways, auto_rot, 'auto_rotate')
    assert auto_rot.is_file()

    bookmarked = tmp_path / 'bookmarked.pdf'
    transform(source, bookmarked, 'bookmarks', toc_text='1 | Chapter One | 1\n1 | Chapter Two | 2')
    with pdf.open(bookmarked) as doc:
        assert len(doc.get_toc()) == 2

    split_zip = tmp_path / 'split.zip'
    transform(source, split_zip, 'split_size', max_mb=0.1)
    with zipfile.ZipFile(split_zip) as archive:
        assert len(archive.namelist()) >= 1


def test_security_attachments_images_redact_and_compress(tmp_path):
    source = _sample_pdf(tmp_path / 'sec.pdf', pages=1)
    # Add an image + attachment + readonly widget + JS catalog entry
    attach_file = tmp_path / 'note.txt'
    attach_file.write_text('hello attachment', encoding='utf-8')
    with_attach = tmp_path / 'attached.pdf'
    transform(source, with_attach, 'attachments', attachment_mode='add', attachment_path=str(attach_file))

    extracted_zip = tmp_path / 'att.zip'
    assert transform(with_attach, extracted_zip, 'attachments', attachment_mode='extract') == 1

    info = inspect_pdf_report(with_attach)
    assert info['attachment_count'] == 1 and info['page_count'] == 1

    # Custom term redaction
    redacted = tmp_path / 'redacted.pdf'
    assert transform(source, redacted, 'redact', custom_terms='SecretWordHere') >= 1
    with pdf.open(redacted) as doc:
        assert 'SecretWordHere' not in doc[0].get_text()

    # Best-effort compression when target is tiny
    tiny_out = tmp_path / 'best.pdf'
    with pdf.open() as doc:
        doc.new_page().insert_text((20, 40), 'Vector text only')
        doc.set_metadata({'subject': 'x' * 80000})
        big_vec = tmp_path / 'vec.pdf'
        doc.save(big_vec)
    transform(big_vec, tiny_out, 'target_size', target_mb=0.05, allow_best_effort=True)
    assert tiny_out.is_file()

    # Unlock readonly form field
    ro_pdf = tmp_path / 'ro_form.pdf'
    with pdf.open() as doc:
        p = doc.new_page()
        w = pdf.Widget()
        w.field_name = 'RO'
        w.field_type = pdf.PDF_WIDGET_TYPE_TEXT
        w.rect = pdf.Rect(50, 50, 200, 80)
        w.field_flags = pdf.PDF_FIELD_IS_READ_ONLY
        p.add_widget(w)
        doc.save(ro_pdf)
    unlocked_forms = tmp_path / 'unlocked_forms.pdf'
    assert transform(ro_pdf, unlocked_forms, 'unlock_forms') == 1
    with pdf.open(unlocked_forms) as doc:
        field = next(doc[0].widgets())
        assert not (field.field_flags & pdf.PDF_FIELD_IS_READ_ONLY)

    # Sanitize active scripts & attachments
    clean_sec = tmp_path / 'clean_sec.pdf'
    transform(with_attach, clean_sec, 'sanitize_scripts')
    with pdf.open(clean_sec) as doc:
        assert not doc.embfile_names()


def test_text_compare_and_pipeline_execution(tmp_path):
    a = _sample_pdf(tmp_path / 'a.pdf', pages=2)
    b = tmp_path / 'b.pdf'
    with pdf.open() as doc:
        p1 = doc.new_page()
        p1.insert_text((60, 80), 'Heading Page 1 Modified', fontsize=20)
        p2 = doc.new_page()
        p2.insert_text((60, 80), 'Heading Page 2', fontsize=20)
        doc.save(b)
    diff = compare_text(a, b)
    assert diff['changed_pages'] >= 1
    assert 'Modified' in diff['text']

    pipe_out = tmp_path / 'piped.pdf'
    steps = [
        {'operation': 'rotate', 'options': {'rotation': 180}},
        {'operation': 'page_numbers', 'options': {'number_start': 1}},
        {'operation': 'metadata', 'options': {}},
    ]
    run_pipeline(a, pipe_out, steps)
    with pdf.open(pipe_out) as doc:
        assert len(doc) == 2
        assert doc[0].rotation == 180
    assert len(TOOLS) >= 50
    assert len(DEFAULT_PIPELINES) >= 4
