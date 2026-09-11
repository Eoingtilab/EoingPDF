"""Opt-in real Office tests; only newly created test documents are touched."""
import json
from pathlib import Path
import sys
import time
import hashlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.convert import to_pdf
import pymupdf as pdf
import pythoncom
import win32com.client

root = Path(__file__).resolve().parents[1] / 'temp/native'
root.mkdir(parents=True, exist_ok=True)
pythoncom.CoInitialize()
results = []
word_kinds = {'word', 'doc', 'rtf'}
excel_kinds = {'excel', 'xls', 'xlsm'}
powerpoint_kinds = {'powerpoint', 'ppt', 'pptm'}
for kind in sys.argv[1:] or ['word', 'excel', 'powerpoint']:
    app = document = None
    started = time.monotonic()
    try:
        if kind in word_kinds:
            source = root / ('sample.' + {'word':'docx','doc':'doc','rtf':'rtf'}[kind])
            app = win32com.client.DispatchEx('Word.Application')
            app.Visible = False
            document = app.Documents.Add()
            document.Content.Text = 'EoingPDF native Word conversion test. Original document remains safe.'
            document.SaveAs2(str(source), {'word':16,'doc':0,'rtf':6}[kind])
            document.Close(False)
            document = None
            app.Quit()
            app = None
        elif kind in excel_kinds:
            source = root / ('sample.' + {'excel':'xlsx','xls':'xls','xlsm':'xlsm'}[kind])
            app = win32com.client.DispatchEx('Excel.Application')
            app.Visible = False
            app.DisplayAlerts = False
            document = app.Workbooks.Add()
            document.Worksheets(1).Cells(1, 1).Value = 'EoingPDF Excel conversion test'
            document.Worksheets(1).Columns(1).ColumnWidth = 50
            document.SaveAs(str(source), {'excel':51,'xls':56,'xlsm':52}[kind])
            document.Close(False)
            document = None
            app.Quit()
            app = None
        elif kind in powerpoint_kinds:
            source = root / ('sample.' + {'powerpoint':'pptx','ppt':'ppt','pptm':'pptm'}[kind])
            app = win32com.client.DispatchEx('PowerPoint.Application')
            document = app.Presentations.Add(False)
            slide = document.Slides.Add(1, 12)
            slide.Shapes.AddTextbox(1, 40, 40, 500, 100).TextFrame.TextRange.Text = 'EoingPDF PowerPoint conversion test'
            document.SaveAs(str(source), {'powerpoint':24,'ppt':1,'pptm':25}[kind])
            document.Close()
            document = None
            # PowerPoint is a singleton: never quit a potentially user-owned app.
            app = None
        else:
            source = root / ('sample.hwpx' if kind == 'hwpx' else 'sample.hwp')
            app = win32com.client.DispatchEx('HWPFrame.HwpObject')
            app.HAction.GetDefault('InsertText', app.HParameterSet.HInsertText.HSet)
            app.HParameterSet.HInsertText.Text = 'EoingPDF Hancom conversion test'
            app.HAction.Execute('InsertText', app.HParameterSet.HInsertText.HSet)
            from eoingpdf.hwp_guard import allow_job
            with allow_job(app, source, source):
                if not app.SaveAs(str(source), 'HWPX' if kind == 'hwpx' else 'HWP', ''):
                    raise RuntimeError('HWP fixture save failed')
            app = None
        output = root / f'{kind}.pdf'
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        to_pdf(source, output, timeout=35)
        assert source_hash == hashlib.sha256(source.read_bytes()).hexdigest(), 'Original changed'
        with pdf.open(output) as doc:
            text = ''.join(p.get_text() for p in doc)
            assert doc.page_count > 0 and 'EoingPDF' in text, repr(text)
            doc[0].get_pixmap(matrix=pdf.Matrix(1, 1)).save(root / f'{kind}.png')
        results.append({'kind': kind, 'ok': True, 'seconds': round(time.monotonic() - started, 2)})
    except Exception as error:
        results.append({'kind': kind, 'ok': False, 'error': str(error), 'seconds': round(time.monotonic() - started, 2)})
    finally:
        if document is not None:
            try:
                document.Close() if kind in powerpoint_kinds else document.Close(False)
            except Exception:
                pass
        if app is not None and kind not in powerpoint_kinds:
            try:
                app.Quit()
            except Exception:
                pass
        print(json.dumps(results[-1], ensure_ascii=True), flush=True)
pythoncom.CoUninitialize()
(root / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
sys.exit(0 if all(result['ok'] for result in results) else 1)
