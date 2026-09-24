"""First-page diagnostics. Timing is measured, never inferred from a target."""
import json
import re
import time
from pathlib import Path
import pymupdf as pdf
from .core import open_pdf
from .advanced import sensitive_matches


def inspect_pdf(path, budget_ms=30, trigger='open'):
    started = time.perf_counter()
    report = {'diagnostics': [], 'partial': False, 'pages_scanned': 0, 'elapsed_ms': 0,
              'suggested_name': '', 'page_count': 0}

    def expired():
        result = (time.perf_counter() - started) * 1000 >= budget_ms
        report['partial'] |= result
        return result

    def add(code, title, action):
        report['diagnostics'].append({'code': code, 'title': title, 'action': action})

    try:
        # Detect locked files before the normal authenticated reader. No password is
        # requested by the background sniffer; the viewer asks only when the user opens it.
        with pdf.open(path) as raw:
            if raw.needs_pass:
                report['page_count'] = raw.page_count
                add('PDF-LOCKED', '암호 PDF · 암호 입력 필요', 'decrypt')
                return report
        with open_pdf(path) as doc:
            report['page_count'] = len(doc)
            if any(doc.metadata.get(key) for key in ('author', 'creator', 'producer', 'modDate')) or doc.xref_xml_metadata():
                add('D-03', '문서 정보 제거', 'metadata')
            if expired():
                return report
            page = doc[0]
            report['pages_scanned'] = 1
            width, height = page.rect.width, page.rect.height
            if len(doc) >= 10 and any(abs(width / max(height, 1) - ratio) < .06 for ratio in (16 / 9, 4 / 3)):
                add('D-04', '슬라이드쇼로 보기', 'presentation')
                add('D-04', '4쪽 모아찍기', 'four_up')
            text = page.get_text('text')
            if expired():
                return report
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                heading = next((line for line in lines[:8] if len(line) >= 3 and not sensitive_matches(line)), '')
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', heading)[:60].strip(' .')
                if name:
                    if name.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
                        name = '_' + name
                    report['suggested_name'] = name + '.pdf'
                    add('D-09', '제목으로 파일명 추천', 'rename')
            fonts = page.get_fonts()
            images = page.get_images()
            if (not text.strip() and images and not fonts) or text.count('\ufffd') > max(2, len(text) * .05):
                add('D-02', '검색 가능한 PDF 만들기', 'searchable')
            if any(word in text for word in ('주민등록', '운전면허', '통장')) and min(width, height) < 595 and max(width, height) < 842:
                add('D-01', '증빙 보정·개인정보 지우기', 'safe_submission')
            if any(word in text for word in ('계약서', '견적서', '합의서')) and any(word in text for word in ('서명', '직인', '날인', '(인)')):
                add('D-06', '서명 포함 이미지 사본', 'flatten')
            if any(True for _ in page.annots() or ()) and not any(item['code'] == 'D-03' for item in report['diagnostics']):
                # Metadata cleanup does not delete comments; do not suggest that it does.
                add('D-03', '주석 포함 · 제출 내용 확인', 'review')
            if expired():
                return report
            compact = ''.join(text.split())
            numeric = sum(char.isdecimal() for char in compact) / max(1, len(compact))
            if numeric >= .4:
                lines_count = sum(item[0] == 'l' for drawing in page.get_drawings() for item in drawing['items'])
                if lines_count >= 4:
                    add('D-07', '숫자 표 · 표 복사', 'table')
            if trigger == 'print' and not expired():
                pixmap = page.get_pixmap(matrix=pdf.Matrix(96 / max(width, height), 96 / max(width, height)),
                                        colorspace=pdf.csGRAY, alpha=False)
                darkness = sum(value < 70 for value in pixmap.samples) / max(1, len(pixmap.samples))
                if darkness >= .7:
                    add('D-05', '어두운 배경 · 밝은 인쇄용 사본', 'print_light')
            image_count = len(page.get_images(full=True))
            if image_count >= 2 and len(doc) > 1:
                add('CONTENT-IMAGES', '여러 이미지 · 페이지 세로 연결', 'stitch')
    except Exception as error:
        report['error'] = '문서 구조를 읽지 못했습니다.'
        report['error_detail'] = type(error).__name__
        add('PDF-DAMAGED', '손상 가능성 · PDF 복구 확인', 'repair')
    finally:
        report['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 3)
        report['within_budget'] = report['elapsed_ms'] <= budget_ms
    return report


def main(arguments):
    if len(arguments) not in (1, 2) or (len(arguments) == 2 and arguments[1] not in {'open', 'print'}):
        return 2
    try:
        result = inspect_pdf(Path(arguments[0]), trigger=arguments[1] if len(arguments) == 2 else 'open')
    except Exception:
        result = {'diagnostics': [], 'error': '문서 진단을 완료하지 못했습니다.'}
    print(json.dumps(result, ensure_ascii=True))
    return 0
