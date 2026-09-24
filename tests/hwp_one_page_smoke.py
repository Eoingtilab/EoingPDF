"""Real Hancom conversion of synthetic documents saved with two-up printing."""
import json
from pathlib import Path
import sys
import tempfile
import os
import subprocess
import pythoncom
import win32com.client
import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eoingpdf.hwp_guard import allow_job, job_directory
from eoingpdf.convert import native_child


def run_case(extension):
    with tempfile.TemporaryDirectory(prefix='hwp-oneup-', dir=ROOT / 'temp') as temporary:
        folder = Path(temporary)
        source, two_up = folder / f'source.{extension}', folder / f'two-up-{extension}.pdf'
        pythoncom.CoInitialize()
        app = None
        try:
            app = win32com.client.DispatchEx('HWPFrame.HwpObject')
            with allow_job(app, source, two_up):
                app.XHwpWindows.Item(0).Visible = False
                for number in range(1, 5):
                    text = app.HParameterSet.HInsertText
                    app.HAction.GetDefault('InsertText', text.HSet)
                    text.Text = f'EOING PAGE {number}'
                    assert app.HAction.Execute('InsertText', text.HSet)
                    if number < 4:
                        assert app.HAction.Run('BreakPage')
                assert int(app.PageCount) == 4
                action = app.CreateAction('PrintToPDFEx')
                parameters = action.CreateSet(); action.GetDefault(parameters)
                for key, value in dict(FileName=str(two_up), PrinterName='Hancom PDF',
                    PrintMethod=4, Range=0, NumCopy=1, PrintToFile=0, ReverseOrder=0).items():
                    parameters.SetItem(key, value)
                assert action.Execute(parameters)
                assert app.SaveAs(str(source), extension.upper(), '')
            app = None
        finally:
            if app is not None:
                try:
                    app.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()
        with pdf.open(two_up) as document:
            assert len(document) == 2, 'Fixture did not actually use two-up printing'
        original = source.read_bytes()
        target, status = folder / f'one-up-{extension}.pdf', folder / f'{extension}.json'
        native_child(str(source), str(target), str(status))
        result = json.loads(status.read_text(encoding='utf-8'))
        assert result['ok'], result
        with pdf.open(target) as document:
            assert len(document) == 4
            for index, page in enumerate(document):
                assert f'EOING PAGE {index + 1}' in page.get_text()
        assert source.read_bytes() == original
        print(f'PASS: real {extension} two-up setting -> 4 individual PDF pages; source preserved', flush=True)


def main(timeout=180):
    # COM calls can block even inside finally/app.Quit. The parent owns the
    # access grant so it can revoke paths after a worker timeout as well.
    for extension in ('hwp', 'hwpx'):
        with job_directory() as directory:
            environment = dict(os.environ, EOINGPDF_HWP_JOB=str(directory))
            try:
                subprocess.run(
                    [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--worker', extension],
                    env=environment, check=True, timeout=timeout,
                )
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(
                    f'{extension}: Hancom did not respond within {timeout} seconds. '
                    'The test worker was stopped; no user Hancom process was terminated. '
                    'Check for an open Hancom dialog before retrying.'
                ) from error


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker' and sys.argv[2] in ('hwp', 'hwpx'):
        run_case(sys.argv[2])
    elif len(sys.argv) == 1:
        main()
    else:
        raise SystemExit('Usage: hwp_one_page_smoke.py [--worker hwp|hwpx]')
