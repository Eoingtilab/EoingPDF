"""Verify real helper termination revokes only its temporary HWP grant."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import winreg
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.convert import to_pdf
from eoingpdf.core import Cancelled
from eoingpdf.hwp_guard import REGISTRY

worker = r'''
import os, time, winreg
from pathlib import Path
d = Path(os.environ['EOINGPDF_HWP_JOB'])
(d/'allowed.txt').write_text('temporary test grant')
with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\HNC\HwpAutomation\Modules') as k:
    winreg.SetValueEx(k, 'EoingPDF_'+d.name, 0, winreg.REG_SZ, str(d/'guard-x86.dll'))
(d/'ready').touch()
time.sleep(60)
'''

real_popen = subprocess.Popen
for mode in ('cancel', 'timeout'):
    state = {}
    def launch(command, **kwargs):
        directory = Path(kwargs['env']['EOINGPDF_HWP_JOB'])
        state['directory'] = directory
        state['process'] = real_popen([sys.executable, '-c', worker], **kwargs)
        deadline = time.monotonic() + 5
        while not (directory / 'ready').exists():
            if time.monotonic() > deadline:
                state['process'].kill()
                raise AssertionError('Fake COM helper did not become ready')
            time.sleep(.01)
        return state['process']
    with tempfile.TemporaryDirectory() as temporary, patch('eoingpdf.convert.subprocess.Popen', launch):
        root = Path(temporary)
        source = root / 'test.hwp'
        source.write_bytes(b'unchanged input')
        try:
            to_pdf(source, root / 'output.pdf', cancelled=lambda: mode == 'cancel', timeout=0)
            raise AssertionError('Expected termination')
        except Cancelled:
            assert mode == 'cancel'
        except ValueError:
            assert mode == 'timeout'
        assert source.read_bytes() == b'unchanged input'
        assert state['process'].poll() is not None
        assert not (state['directory'] / 'allowed.txt').exists()
        assert not state['directory'].exists()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY) as key:
            try:
                winreg.QueryValueEx(key, 'EoingPDF_' + state['directory'].name)
                raise AssertionError('Temporary registration survived')
            except FileNotFoundError:
                pass
    print(f'PASS: HWP {mode}, helper stopped, grant revoked, original preserved')
