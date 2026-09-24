import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf as pdf
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.advanced import transform, sensitive_matches, luhn
from eoingpdf.core import open_pdf, pages_from_text, Cancelled


class AdvancedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.source = self.folder / 'source.pdf'
        with pdf.open() as doc:
            for index in range(3):
                page = doc.new_page()
                page.insert_text((72, 100), f'PAGE {index + 1}')
            doc.save(self.source)
        self.original = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original)
        self.assertFalse(list(self.folder.glob('.eoing-*')))

    def test_password_roundtrip_and_permissions(self):
        encrypted = self.folder / 'locked.pdf'
        transform(self.source, encrypted, 'encrypt', user_password='reader', owner_password='owner')
        with pdf.open(encrypted) as doc:
            self.assertTrue(doc.needs_pass)
            self.assertFalse(doc.authenticate('incorrect'))
            self.assertTrue(doc.authenticate('reader'))
            self.assertTrue(doc.permissions & pdf.PDF_PERM_PRINT)
            self.assertFalse(doc.permissions & pdf.PDF_PERM_COPY)
        unlocked = self.folder / 'unlocked.pdf'
        with self.assertRaises(ValueError):
            transform(encrypted, unlocked, 'decrypt', password='incorrect')
        self.assertFalse(unlocked.exists())
        transform(encrypted, unlocked, 'decrypt', password='reader')
        with open_pdf(unlocked) as doc:
            self.assertEqual(len(doc), 3)

    def test_reverse_and_end_parser(self):
        output = self.folder / 'reverse.pdf'
        transform(self.source, output, 'reverse')
        with open_pdf(output) as doc:
            self.assertIn('PAGE 3', doc[0].get_text())
        self.assertEqual(pages_from_text('1-2, 3-end', 4), [0, 1, 2, 3])

    def test_blank_does_not_remove_vector_only_page(self):
        fixture = self.folder / 'blank.pdf'
        with pdf.open() as doc:
            doc.new_page()
            page = doc.new_page()
            page.draw_line((10, 10), (100, 10))
            doc.save(fixture)
        output = self.folder / 'clean.pdf'
        self.assertEqual(transform(fixture, output, 'remove_blank'), 1)
        with open_pdf(output) as doc:
            self.assertEqual(len(doc), 1)
            self.assertTrue(doc[0].get_drawings())

    def test_redaction_destroys_text_stream(self):
        fixture = self.folder / 'pii.pdf'
        email = 'person@example.com'
        with pdf.open() as doc:
            page = doc.new_page()
            page.insert_text((30, 50), email)
            page.insert_text((30, 80), 'KEEP THIS')
            doc.save(fixture)
        output = self.folder / 'redacted.pdf'
        self.assertEqual(transform(fixture, output, 'redact'), 1)
        with open_pdf(output) as doc:
            self.assertNotIn(email, doc[0].get_text())
            self.assertIn('KEEP THIS', doc[0].get_text())
            for xref in range(1, doc.xref_length()):
                if doc.xref_is_stream(xref):
                    raw = doc.xref_stream(xref)
                    self.assertNotIn(email.encode(), raw)
                    self.assertNotIn(email.encode().hex().encode(), raw.lower())
        self.assertTrue(luhn('4111 1111 1111 1111'))
        self.assertFalse(luhn('4111 1111 1111 1112'))
        self.assertIn('010-1234-5678', sensitive_matches('Call 010-1234-5678'))

    def test_split_and_trim(self):
        split = self.folder / 'split.pdf'
        transform(self.source, split, 'split_spread')
        with open_pdf(split) as doc:
            self.assertEqual(len(doc), 6)
            self.assertAlmostEqual(doc[0].rect.width, 595 / 2)
        trim = self.folder / 'trim.pdf'
        transform(self.source, trim, 'trim')
        with open_pdf(trim) as doc:
            self.assertLess(doc[0].rect.width, 595)
            self.assertIn('PAGE 1', doc[0].get_text())

    def test_cancel_and_existing_target(self):
        output = self.folder / 'cancel.pdf'
        with self.assertRaises(Cancelled):
            transform(self.source, output, 'reverse', cancelled=lambda: True)
        self.assertFalse(output.exists())
        with self.assertRaises(ValueError):
            transform(self.source, self.source, 'reverse')

    def test_flatten_resolution_and_visible_annotation(self):
        fixture, target = self.folder / 'note.pdf', self.folder / 'flat.pdf'
        with pdf.open() as doc:
            page = doc.new_page(width=144, height=72)
            page.insert_text((10, 30), 'Original')
            page.add_rect_annot(pdf.Rect(5, 5, 100, 60)).update()
            doc.save(fixture)
        transform(fixture, target, 'flatten')
        with open_pdf(target) as doc:
            self.assertEqual(doc[0].get_text(), '')
            images = doc[0].get_images()
            self.assertEqual((images[0][2], images[0][3]), (600, 300))
            self.assertEqual(len(list(doc[0].annots() or ())), 0)

    def test_metadata_removed(self):
        fixture, target = self.folder / 'metadata.pdf', self.folder / 'clean-metadata.pdf'
        with pdf.open() as doc:
            doc.new_page()
            doc.set_metadata({'author': 'Synthetic Author', 'creator': 'Synthetic Creator'})
            doc.set_xml_metadata('<x:xmpmeta xmlns:x="adobe:ns:meta/">synthetic</x:xmpmeta>')
            doc.save(fixture)
        transform(fixture, target, 'metadata')
        with open_pdf(target) as doc:
            self.assertFalse(doc.metadata.get('author'))
            self.assertFalse(doc.metadata.get('creator'))
            self.assertFalse(doc.get_xml_metadata())
