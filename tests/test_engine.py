import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pymupdf as pdf
from PIL import Image
from eoingpdf.core import Request, run, pages_from_text, Cancelled
from eoingpdf.convert import to_pdf, text_pdf
from eoingpdf.jobs import execute
from eoingpdf.summary import summarize


class EngineTests(unittest.TestCase):
    def test_merge_cancel_is_not_a_failure(self):
        from unittest.mock import patch
        with patch('eoingpdf.jobs.run', side_effect=Cancelled('cancelled')):
            result = execute('merge', [str(self.source)], str(self.root / 'out'))
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['outputs'], [])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'original.pdf'
        with pdf.open() as doc:
            for index in range(3):
                page = doc.new_page()
                page.insert_text((50, 50), f'Page {index + 1}. The document processing project protects original files. Fast conversion supports daily work.')
            doc.save(self.source)
        self.before = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(self.before, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.tmp.cleanup()

    def run_tool(self, tool, pages='', **kwargs):
        return run(Request(tool, (str(self.source),), str(self.root), pages, **kwargs))

    def test_reorder_and_duplicate(self):
        result = self.run_tool('extract', '3,1,1')
        with pdf.open(result) as doc:
            self.assertEqual(doc.page_count, 3)
            self.assertIn('Page 3', doc[0].get_text())
            self.assertIn('Page 1', doc[2].get_text())

    def test_invalid_ranges(self):
        for value in ['0', '4', 'x', '1-', '1,,2', '-1', '1-999999999999', '999999999999-1']:
            with self.assertRaises(ValueError):
                pages_from_text(value, 3)
        self.assertEqual(pages_from_text('3-1', 3), [2, 1, 0])

    def test_rotate_only_selected(self):
        result = self.run_tool('rotate', '2,2', rotation=90)
        with pdf.open(result) as doc:
            self.assertEqual([p.rotation for p in doc], [0, 90, 0])

    def test_output_collision(self):
        first = self.run_tool('optimize')
        before = first.read_bytes()
        second = self.run_tool('optimize')
        self.assertNotEqual(first, second)
        self.assertEqual(before, first.read_bytes())

    def test_png_and_text(self):
        image = self.run_tool('png', '1,3')
        with zipfile.ZipFile(image) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            self.assertTrue(archive.read(archive.namelist()[0]).startswith(b'\x89PNG'))
        result = self.run_tool('text', '2')
        self.assertIn('Page 2', result.read_text(encoding='utf-8-sig'))

    def test_number(self):
        result = self.run_tool('number', '2')
        with pdf.open(result) as doc:
            self.assertIn('2 / 3', doc[1].get_text())
            self.assertNotIn('1 / 3', doc[0].get_text())

    def test_cancel_cleans_scratch(self):
        with self.assertRaises(Cancelled):
            run(Request('merge', (str(self.source),), str(self.root)), cancelled=lambda: True)
        self.assertFalse(list(self.root.glob('.eoing-*')))

    def test_encrypted_rejected(self):
        encrypted = self.root / 'locked.pdf'
        with pdf.open(self.source) as doc:
            doc.save(encrypted, encryption=pdf.PDF_ENCRYPT_AES_256, user_pw='test', owner_pw='owner')
        with self.assertRaises(ValueError):
            run(Request('text', (str(encrypted),), str(self.root)))

    def test_korean_text_roundtrip(self):
        text = self.root / '한글.txt'
        text.write_text('어잉PDF 문서 변환 테스트\n원본을 보호하면서 빠르게 문서를 변환합니다.', encoding='cp949')
        output = self.root / '한글.pdf'
        to_pdf(text, output)
        with pdf.open(output) as doc:
            self.assertIn('원본을 보호', doc[0].get_text().replace('\xa0', ' '))

    def test_mixed_merge(self):
        image = self.root / 'image.png'
        Image.new('RGB', (100, 120), 'blue').save(image)
        text = self.root / 'text.txt'
        text.write_text('Mixed documents', encoding='utf-8')
        result = execute('merge', [self.source, image, text], self.root)
        self.assertFalse(result['errors'])
        with pdf.open(result['outputs'][0]) as doc:
            self.assertEqual(doc.page_count, 5)

    def test_multiframe_tiff(self):
        image = self.root / 'scan.tiff'
        Image.new('RGB', (100, 100), 'white').save(image, save_all=True, append_images=[Image.new('RGB', (100, 100), 'blue')])
        output = self.root / 'scan.pdf'
        to_pdf(image, output)
        with pdf.open(output) as doc:
            self.assertEqual(doc.page_count, 2)

    def test_summary_provenance(self):
        text = summarize(self.source)
        self.assertIn('[p.', text)
        self.assertIn('생성형 AI 요약이 아니며', text)
        self.assertIn('protects original files', text)

    def test_summary_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            summarize(self.source, limit=0)
        with self.assertRaises(ValueError):
            summarize(self.source, limit=21)

    def test_partial_failure_is_explicit(self):
        bad = self.root / 'bad.pdf'
        bad.write_text('not a pdf')
        result = execute('convert', [self.source, bad], self.root)
        self.assertEqual(len(result['outputs']), 1)
        self.assertEqual(len(result['errors']), 1)
        result = execute('merge', [self.source, bad], self.root)
        self.assertFalse(result['outputs'])
        self.assertEqual(len(result['errors']), 1)


if __name__ == '__main__':
    unittest.main()
