import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf as pdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.libreoffice import convert
from eoingpdf.core import Cancelled


class LibreOfficeTests(unittest.TestCase):
    def test_isolated_profile_and_validated_output(self):
        commands = []

        class Process:
            returncode = 0

            def __init__(self, command, **kwargs):
                commands.append(command)
                out = Path(command[command.index('--outdir') + 1])
                profile = out.parent / 'profile/user/registrymodifications.xcu'
                self_test.assertIn('<value>3</value>', profile.read_text(encoding='utf-8'))
                with pdf.open() as doc:
                    doc.new_page().insert_text((30, 50), 'converted')
                    doc.save(out / (Path(command[-1]).stem + '.pdf'))

            def poll(self):
                return 0

        self_test = self
        with tempfile.TemporaryDirectory() as folder, patch('eoingpdf.libreoffice.subprocess.Popen', Process):
            source, target = Path(folder) / '한글 이름.docx', Path(folder) / 'output.pdf'
            source.write_bytes(b'test')
            convert(source, target, executable='test-soffice')
            with pdf.open(target) as doc:
                self.assertIn('converted', doc[0].get_text())
            self.assertEqual(source.read_bytes(), b'test')
        self.assertEqual(len(commands), 1)
        self.assertTrue(commands[0][1].startswith('-env:UserInstallation=file:///'))
        self.assertFalse(Path(commands[0][commands[0].index('--outdir') + 1]).exists())

    def test_missing_dependency_and_cancel(self):
        with patch('eoingpdf.libreoffice.find_executable', return_value=None):
            with self.assertRaisesRegex(ValueError, 'LibreOffice'):
                convert('source.docx', 'target.pdf')
        with patch('eoingpdf.libreoffice.subprocess.Popen') as process:
            with self.assertRaises(Cancelled):
                convert('source.docx', 'target.pdf', executable='test', cancelled=lambda: True)
            process.assert_not_called()
