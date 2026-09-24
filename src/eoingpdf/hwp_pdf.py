"""Explicit one-document-page-per-PDF-page Hancom export."""
from .localization import tr
from pathlib import Path
import time
import pymupdf as pdf


def export_pdf(app, target):
    import win32print
    target = Path(target).resolve()
    if target.exists():
        raise ValueError(tr('한글 변환 대상 파일이 이미 있습니다.'))
    printers = {entry[2] for entry in win32print.EnumPrinters(2 | 4)}
    if 'Hancom PDF' not in printers:
        raise ValueError(tr('한 쪽씩 변환하려면 한컴 PDF 구성 요소가 필요합니다.'))
    expected = int(app.PageCount)
    if expected < 1:
        raise ValueError(tr('한글 문서의 페이지 수를 확인하지 못했습니다.'))
    action = app.CreateAction('PrintToPDFEx')
    parameters = action.CreateSet()
    action.GetDefault(parameters)
    for name, value in {
        'FileName': str(target), 'PrinterName': 'Hancom PDF',
        'PrintMethod': 0, 'Range': 0, 'RangeCustom': '', 'NumCopy': 1, 'Collate': 1,
        'UserOrder': 0, 'UsingPagenum': 0, 'ReverseOrder': 0,
        'Pause': 0, 'PrintToFile': 0,
        'PrintImage': 1, 'PrintDrawObj': 1, 'PrintFormObj': 1,
        'PrintAutoHeadNote': 0, 'PrintAutoFootNote': 0,
        'PrintAutoHeadnoteLtext': '', 'PrintAutoHeadnoteCtext': '', 'PrintAutoHeadnoteRtext': '',
        'PrintAutoFootnoteLtext': '', 'PrintAutoFootnoteCtext': '', 'PrintAutoFootnoteRtext': '',
        'PrintMemo': 0, 'PrintMemoContents': 0,
    }.items():
        parameters.SetItem(name, value)
    if not action.Execute(parameters):
        raise ValueError(tr('한글의 한 쪽씩 PDF 변환을 실행하지 못했습니다.'))
    deadline = time.monotonic() + 30
    while True:
        try:
            with pdf.open(target) as document:
                if not document.is_pdf or document.page_count != expected:
                    raise ValueError(tr('한글 원문 {v0}쪽과 변환된 PDF 페이지 수가 일치하지 않습니다.', v0=expected))
            return
        except (OSError, pdf.FileDataError):
            if time.monotonic() >= deadline:
                raise ValueError(tr('한글 PDF 출력을 완료하지 못했습니다.'))
            time.sleep(.1)
