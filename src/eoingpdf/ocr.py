"""Use the Windows OCR language pack without uploading or bundling a model."""
from pathlib import Path
import subprocess
import tempfile
import time
import pymupdf as pdf


def page_text(page, cancelled=lambda: False):
    text = page.get_text(sort=True).replace('\xa0', ' ')
    if len(text.strip()) >= 12 or not page.get_images():
        return text, False
    from .convert import ROOT
    from .core import Cancelled
    executable = ROOT / 'assets/EoingPDF.Ocr.exe'
    if not executable.is_file():
        raise ValueError('Windows OCR 연결 파일이 없습니다. 배포 폴더를 다시 확인해 주세요.')
    with tempfile.TemporaryDirectory(prefix='eoing-ocr-') as temporary:
        folder = Path(temporary)
        image_path, text_path = folder / 'page.png', folder / 'text.txt'
        scale = min(3, 2400 / max(page.rect.width, page.rect.height))
        page.get_pixmap(matrix=pdf.Matrix(scale, scale), alpha=False).save(image_path)
        process = subprocess.Popen([str(executable), str(image_path), str(text_path)],
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancelled():
                    raise Cancelled('작업을 취소했습니다.')
                if time.monotonic() - started > 30:
                    raise ValueError('글자 인식 시간이 초과됐습니다. 페이지를 나눠 다시 시도해 주세요.')
                time.sleep(.05)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        if process.returncode == 3:
            raise ValueError('Windows OCR 언어가 없습니다. Windows 언어 설정에서 한국어 OCR을 설치해 주세요.')
        if process.returncode != 0 or not text_path.is_file():
            raise ValueError('이 페이지의 글자를 인식하지 못했습니다. 이미지 상태와 Windows OCR 언어를 확인해 주세요.')
        return text_path.read_text(encoding='utf-8'), True
