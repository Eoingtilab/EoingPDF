"""Native format conversion with isolated, time-limited Office automation."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import pymupdf as pdf
from .core import IMAGES, Cancelled, open_pdf

OFFICE = {'.doc', '.docx', '.rtf', '.xls', '.xlsx', '.xlsm', '.ppt', '.pptx', '.pptm', '.hwp', '.hwpx'}
TEXT = {'.txt', '.csv', '.md'}
SUPPORTED = IMAGES | OFFICE | TEXT | {'.pdf'}
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))


def read_text(path):
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('텍스트 파일은 20MB 이하로 선택해 주세요.')
    raw = path.read_bytes()
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16')
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError('텍스트 인코딩을 읽을 수 없습니다. UTF-8로 저장한 뒤 다시 시도해 주세요.')


def text_pdf(text, target, cancelled=lambda: False):
    font_path = ROOT / 'assets/fonts/Pretendard-Regular.ttf'
    font = pdf.Font(fontfile=str(font_path))
    with pdf.open() as doc:
        page = None
        y = 0
        for original in text.replace('\t', '    ').splitlines() or ['']:
            if cancelled():
                raise Cancelled('작업을 취소했습니다.')
            chunks, line, width = [], '', 0
            for char in original:
                advance = font.text_length(char, fontsize=11)
                if width + advance > 499 and line:
                    chunks.append(line)
                    line, width = '', 0
                line += char
                width += advance
            chunks.append(line)
            for line in chunks:
                if page is None or y > 790:
                    page = doc.new_page(width=595, height=842)
                    page.insert_font(fontname='pretendard', fontfile=str(font_path))
                    y = 52
                page.insert_text((48, y), line, fontsize=11, fontname='pretendard', color=(.12, .16, .23))
                y += 17
        doc.subset_fonts()
        doc.save(target, garbage=4, deflate=True)


def to_pdf(source, target, cancelled=lambda: False, timeout=90):
    source, target = Path(source), Path(target)
    ext = source.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f'지원하지 않는 형식입니다: {ext}')
    if ext == '.pdf':
        with open_pdf(source) as doc:
            doc.save(target, garbage=4, deflate=True)
    elif ext in TEXT:
        text_pdf(read_text(source), target, cancelled)
    elif ext in IMAGES:
        # Pillow iterates multi-frame TIFF and applies phone-photo EXIF rotation.
        from PIL import Image, ImageOps, ImageSequence
        import io
        with pdf.open() as doc, Image.open(source) as image:
            for frame in ImageSequence.Iterator(image):
                if cancelled():
                    raise Cancelled('작업을 취소했습니다.')
                corrected = ImageOps.exif_transpose(frame).convert('RGB')
                stream = io.BytesIO()
                corrected.save(stream, format='PNG')
                width, height = corrected.size
                scale = min(1, 14400 / max(width, height))
                page = doc.new_page(width=width * scale, height=height * scale)
                page.insert_image(page.rect, stream=stream.getvalue())
            doc.save(target, garbage=4, deflate=True)
    else:
        result_file = target.with_suffix('.status.json')
        command = [sys.executable]
        if not getattr(sys, 'frozen', False):
            command += [str(ROOT / 'main.py')]
        command += ['--convert-child', str(source), str(target), str(result_file)]
        from contextlib import nullcontext
        from .hwp_guard import job_directory
        with job_directory() if ext in {'.hwp', '.hwpx'} else nullcontext(None) as directory:
            environment = os.environ.copy()
            environment.pop('EOINGPDF_HWP_JOB', None)
            if directory:
                environment['EOINGPDF_HWP_JOB'] = str(directory)
            process = subprocess.Popen(command, env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            started = time.monotonic()
            try:
                while process.poll() is None:
                    if cancelled():
                        raise Cancelled('작업을 취소했습니다.')
                    if time.monotonic() - started > timeout:
                        raise ValueError('문서 변환 시간이 초과됐습니다. Office/한글의 확인창과 문서 상태를 확인해 주세요.')
                    time.sleep(.1)
                status = json.loads(result_file.read_text(encoding='utf-8')) if result_file.exists() else {}
            finally:
                if process.poll() is None:
                    process.kill()  # Only our conversion helper, never all Office processes.
                    process.wait(timeout=5)
                result_file.unlink(missing_ok=True)
        if process.returncode != 0 or not status.get('ok'):
            raise ValueError(status.get('error', '변환 앱을 실행하지 못했습니다. 해당 Office 또는 한글 설치를 확인해 주세요.'))
    with open_pdf(target):
        pass


def native_child(source, target, status_path):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = document = None
    ext = Path(source).suffix.lower()
    owns_app = True
    status = {'ok': False}
    try:
        if ext in {'.doc', '.docx', '.rtf'}:
            app = win32com.client.DispatchEx('Word.Application')
            app.Visible = False
            app.DisplayAlerts = 0
            app.AutomationSecurity = 3
            app.Options.UpdateLinksAtOpen = False
            document = app.Documents.Open(str(source), ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False, PasswordDocument='', WritePasswordDocument='', Visible=False, OpenAndRepair=False)
            document.ExportAsFixedFormat(str(target), 17, OpenAfterExport=False)
        elif ext in {'.xls', '.xlsx', '.xlsm'}:
            app = win32com.client.DispatchEx('Excel.Application')
            app.Visible = False
            app.DisplayAlerts = False
            app.AutomationSecurity = 3
            app.AskToUpdateLinks = False
            document = app.Workbooks.Open(str(source), UpdateLinks=0, ReadOnly=True, Password='', WriteResPassword='', IgnoreReadOnlyRecommended=True, AddToMru=False)
            document.ExportAsFixedFormat(0, str(target), OpenAfterPublish=False)
        elif ext in {'.ppt', '.pptx', '.pptm'}:
            # PowerPoint can reuse its singleton even with DispatchEx. Do not quit it.
            app = win32com.client.DispatchEx('PowerPoint.Application')
            owns_app = False
            original_security = app.AutomationSecurity
            try:
                app.AutomationSecurity = 3
                document = app.Presentations.Open(str(source), ReadOnly=True, Untitled=False, WithWindow=False)
                document.SaveAs(str(target), 32)
            finally:
                app.AutomationSecurity = original_security
        else:
            app = win32com.client.DispatchEx('HWPFrame.HwpObject')
            from .hwp_guard import allow_job
            with allow_job(app, source, target):
                if not app.Open(str(source), '', 'forceopen:true'):
                    raise ValueError('한글에서 파일을 열지 못했습니다.')
                if not app.SaveAs(str(target), 'PDF', ''):
                    raise ValueError('한글 PDF 저장에 실패했습니다.')
            app = None
        status = {'ok': True}
    except Exception as error:
        name = '한컴 한글' if ext in {'.hwp', '.hwpx'} else 'Microsoft Office'
        status = {'ok': False, 'error': f'{name}에서 변환하지 못했습니다. 설치·인증 상태와 암호/확인창을 확인해 주세요.', 'detail': str(error)}
    finally:
        if document is not None:
            try:
                if ext in {'.ppt', '.pptx', '.pptm'}:
                    document.Close()
                else:
                    document.Close(False)
            except Exception:
                pass
        if app is not None and owns_app:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
        Path(status_path).write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
    return 0 if status['ok'] else 1
