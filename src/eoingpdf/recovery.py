"""Rebuild a readable PDF's cross references and verify its recoverable pages."""
from .localization import tr
import hashlib
import pymupdf as pdf
from .core import Cancelled


def fingerprint(page):
    rect = page.rect
    if rect.is_empty or rect.is_infinite:
        raise ValueError(tr('페이지 크기가 손상되어 복구 결과를 검증할 수 없습니다.'))
    scale = min(1, 768 / max(rect.width, rect.height))
    raster = page.get_pixmap(matrix=pdf.Matrix(scale, scale), colorspace=pdf.csRGB, alpha=False)
    digest = hashlib.sha256(raster.samples).digest()
    text = hashlib.sha256(page.get_text().encode('utf-8')).digest()
    return tuple(rect), raster.width, raster.height, digest, text


def rebuild(document, target, cancelled=lambda: False, progress=lambda value: None):
    if not document.is_pdf or not len(document):
        raise ValueError(tr('복구 가능한 PDF 페이지를 찾지 못했습니다.'))
    original = []
    for index, page in enumerate(document):
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        original.append(fingerprint(page))
        progress(int((index + 1) / len(document) * 40))
    if cancelled():
        raise Cancelled(tr('작업을 취소했습니다.'))
    document.save(target, garbage=4, deflate=True, encryption=pdf.PDF_ENCRYPT_NONE)
    with pdf.open(target) as restored:
        if restored.is_repaired or len(restored) != len(original):
            raise ValueError(tr('교차 참조 구조 또는 페이지 수 검증에 실패했습니다.'))
        for index, page in enumerate(restored):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            if fingerprint(page) != original[index]:
                raise ValueError(tr('{v0}페이지의 복구 전후 내용이 달라 저장하지 않았습니다.', v0=index + 1))
            progress(45 + int((index + 1) / len(original) * 45))
    return len(original)
