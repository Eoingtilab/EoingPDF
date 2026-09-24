"""Use the Windows OCR language pack without uploading or bundling a model."""
from .localization import tr
from pathlib import Path
import subprocess
import json
import tempfile
import time
import pymupdf as pdf


def page_layout(page, cancelled=lambda: False):
    from .convert import ROOT
    from .core import Cancelled
    executable = ROOT / 'assets/EoingPDF.Ocr.exe'
    if not executable.is_file():
        raise ValueError(tr('Windows OCR 연결 파일이 없습니다. 배포 폴더를 다시 확인해 주세요.'))
    with tempfile.TemporaryDirectory(prefix='eoing-ocr-') as temporary:
        folder = Path(temporary)
        image_path, text_path = folder / 'page.png', folder / 'layout.json'
        scale = min(3, 2400 / max(page.rect.width, page.rect.height))
        page.get_pixmap(matrix=pdf.Matrix(scale, scale), alpha=False).save(image_path)
        process = subprocess.Popen([str(executable), str(image_path), str(text_path), '--json'],
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                if time.monotonic() - started > 30:
                    raise ValueError(tr('글자 인식 시간이 초과됐습니다. 페이지를 나눠 다시 시도해 주세요.'))
                time.sleep(.05)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        if process.returncode == 3:
            raise ValueError(tr('Windows OCR 언어가 없습니다. Windows 언어 설정에서 한국어 OCR을 설치해 주세요.'))
        if process.returncode != 0 or not text_path.is_file():
            raise ValueError(tr('이 페이지의 글자를 인식하지 못했습니다. 이미지 상태와 Windows OCR 언어를 확인해 주세요.'))
        if text_path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(tr('글자 인식 결과가 너무 큽니다.'))
        result = json.loads(text_path.read_text(encoding='utf-8'))
        if not isinstance(result, dict) or result.get('width', 0) <= 0 or result.get('height', 0) <= 0 or not isinstance(result.get('lines'), list):
            raise ValueError(tr('글자 인식 결과를 읽을 수 없습니다.'))
        return result


def page_text(page, cancelled=lambda: False):
    text = page.get_text(sort=True).replace('\xa0', ' ')
    if len(text.strip()) >= 12 or not page.get_images():
        return text, False
    result = page_layout(page, cancelled)
    return '\n'.join(line['text'] for line in result['lines']), True


def add_searchable_layer(page, cancelled=lambda: False):
    existing = page.get_text()
    damaged = existing.strip() and (
        existing.count('\ufffd') > max(2, len(existing) * .05) or
        existing.count('\u00b7') > max(2, len(existing) * .5)
    )
    if existing.strip() and not damaged:
        return 0
    if damaged:
        # Remove the broken text layer before OCR so replacement glyphs do not remain
        # searchable beside the repaired invisible layer. Images are untouched.
        spans = []
        for block in page.get_text('dict').get('blocks', ()):
            for line in block.get('lines', ()):
                for span in line.get('spans', ()):
                    if span.get('text'):
                        rect = pdf.Rect(span['bbox'])
                        if not rect.is_empty:
                            page.add_redact_annot(rect, fill=False)
                            spans.append(rect)
        if spans:
            page.apply_redactions(images=0, graphics=0, text=0)
    from .convert import ROOT
    layout = page_layout(page, cancelled)
    font_path = ROOT / 'assets/fonts/Pretendard-Regular.ttf'
    font = pdf.Font(fontfile=str(font_path))
    page.insert_font(fontname='EoingOCR', fontfile=str(font_path))
    sx, sy = page.rect.width / layout['width'], page.rect.height / layout['height']
    words = 0
    for line in layout['lines']:
        for word in line['words']:
            if cancelled():
                from .core import Cancelled
                raise Cancelled(tr('작업을 취소했습니다.'))
            text = word['text']
            x, y, width, height = word['box']
            if not text.strip() or min(width, height) <= 0:
                continue
            size = height * sy / (font.ascender - font.descender)
            baseline = pdf.Point(x * sx, y * sy + font.ascender * size)
            baseline = baseline * page.derotation_matrix
            natural_width = font.text_length(text, fontsize=size)
            if natural_width <= 0:
                continue
            scale = width * sx / natural_width
            page.insert_text(baseline, text, fontsize=size, fontname='EoingOCR',
                             render_mode=3, morph=(baseline, pdf.Matrix(scale, 1) * pdf.Matrix(page.rotation)))
            words += 1
    return words
