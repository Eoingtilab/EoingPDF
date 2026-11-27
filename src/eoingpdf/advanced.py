"""Local PDF transformations with authenticated input and atomic new-file output."""
from .localization import tr
import os
import re
import tempfile
import zipfile
from pathlib import Path

import pymupdf as pdf
from .core import Cancelled, open_pdf

TOOLS = {
    'encrypt': ('암호 설정', '열기 암호와 소유자 암호를 구분하여 AES-256으로 저장합니다.'),
    'decrypt': ('암호 해제', '현재 암호를 알고 있는 PDF를 암호 없는 새 사본으로 저장합니다.'),
    'reverse': ('페이지 역순', '마지막 페이지부터 첫 페이지 순서로 새 문서를 만듭니다.'),
    'split_spread': ('책 스캔 좌우 분리', '각 페이지의 왼쪽과 오른쪽을 두 페이지로 나눕니다.'),
    'remove_blank': ('빈 페이지 제거', '텍스트·이미지·도형·주석이 없는 페이지만 보수적으로 제거합니다.'),
    'trim': ('여백 자르기', '본문·이미지·도형의 경계를 기준으로 여백을 줄입니다.'),
    'metadata': ('메타데이터·추적점 소독', '문서 정보와 XMP를 제거하고 발견 가능한 제로폭 문자와 작은 노란 추적점을 지웁니다. 모든 포렌식 흔적 제거를 보장하지는 않습니다.'),
    'smart_dark': ('스마트 다크 PDF', '배경과 텍스트를 어둡게 바꾸고 사진·삽입 이미지는 원래 색을 유지한 새 PDF를 만듭니다. 결과는 이미지 PDF라 텍스트 검색은 사라집니다.'),
    'print_light': ('밝은 인쇄용 사본', '어두운 배경이 대부분인 페이지의 무채색 배경·글자를 반전합니다. 삽입 이미지와 유색 도형은 유지합니다. 결과는 300DPI 이미지 PDF이며 저장 후 비교해 확인하세요.'),
    'redact': ('개인정보 지우기', '텍스트의 주민번호·전화·이메일·카드·SSN을 찾아 실제 삭제합니다. 스캔 이미지는 탐지하지 않으므로 결과를 확인하세요.'),
    'flatten': ('300DPI 이미지 사본', '주석까지 포함한 화면을 300DPI PNG로 합칩니다. 텍스트 검색은 사라지며 이미지 복제는 막을 수 없습니다.'),
    'deskew': ('스캔 기울기 보정', '문서의 선과 모서리를 분석해 수평으로 보정합니다. 결과는 300DPI 이미지 PDF로 저장합니다.'),
    'deskew_bw': ('기울기·흑백 보정', '수평 보정과 고대비 흑백 처리를 적용합니다. 사진과 색상은 흑백으로 변합니다.'),
    'safe_submission': ('증빙 보정·개인정보 지우기', '기울기와 종이 그림자를 보정하고 인식한 개인정보를 실제 삭제합니다. OCR 누락 가능성이 있으므로 원본과 비교해 확인하세요. 결과는 300DPI 이미지 PDF입니다.'),
    'searchable': ('검색 가능한 PDF', 'Windows 로컬 OCR로 스캔에 투명 텍스트를 추가합니다. 인식 결과를 확인해 주세요.'),
    'ocr_redact': ('스캔 개인정보 지우기', '스캔을 OCR로 읽은 뒤 개인정보 영역의 이미지와 텍스트를 삭제합니다. 누락 가능성이 있어 제출 전 확인이 필요합니다.'),
    'watermark_text': ('문구 워터마크', '모든 페이지에 45도 대각선 문구를 넣습니다. 원본 위에 반투명하게 표시합니다.'),
    'watermark_png': ('PNG 워터마크', '투명 PNG를 페이지 중앙에 넣습니다. 기존 투명도와 선택한 불투명도를 함께 적용합니다.'),
    'split_ranges': ('범위별 분할', '1-3, 5, 8-end처럼 입력하면 쉼표로 구분한 범위마다 PDF를 만들어 ZIP으로 저장합니다.'),
    'split_groups': ('페이지 수로 분할', '한 페이지씩 또는 지정한 페이지 수씩 묶어 PDF들을 ZIP으로 저장합니다.'),
    'split_toc': ('목차별 분할', '최상위 목차의 시작 페이지를 기준으로 나눕니다. 첫 목차 이전 페이지도 별도 PDF로 보존합니다.'),
    'target_size': ('목표 용량 압축', '이미지 해상도와 JPEG 품질을 조정합니다. 텍스트·도형은 유지하며 목표 이하의 결과만 저장합니다.'),
    'repair': ('손상 PDF 복구', '읽을 수 있는 페이지를 유지하며 교차 참조 구조를 재작성합니다. 이미 유실된 내용은 복원할 수 없으므로 결과를 확인해 주세요.'),
    'markdown': ('Markdown 내보내기', '제목·본문·표를 Markdown 파일로 추출합니다. 이미지와 복잡한 읽기 순서는 원문을 확인해 주세요.'),
    'four_up': ('4쪽 모아찍기', 'A4 가로 한 면에 4페이지를 배치합니다. 저장한 PDF를 실제 크기로 인쇄해 주세요.'),
    'booklet': ('소책자 인쇄 배치', 'A4 가로 양면을 접어 읽는 순서로 배치합니다. 부족한 쪽은 비워 둡니다. 짧은 쪽 넘김·실제 크기로 인쇄하고 먼저 시험 인쇄해 주세요.'),
    'outlines': ('글꼴 윤곽선 PDF', '글자를 벡터 도형으로 바꾼 인쇄용 사본을 만듭니다. 글자 검색·편집과 양식 입력·링크는 사라지며 이미지와 페이지 크기는 유지합니다. 인쇄 전 결과를 확인하세요.'),
    'dxf': ('DXF 도형 경로 내보내기', '직선·베지에 곡선·도형 윤곽을 mm 단위 CAD 파일로 추출합니다. 페이지별 ZIP 저장. 글자·이미지·채움·점선·클리핑 효과는 제외하므로 CAD 작업 전 확인하세요.'),
    'svg': ('SVG 벡터 내보내기', '페이지별 SVG를 ZIP으로 저장합니다. 글자는 윤곽선으로, 이미지는 포함된 이미지로 내보냅니다.'),
    'stitch': ('페이지 세로 연결', '페이지를 같은 너비로 맞춰 간격 없이 한 페이지로 연결합니다. 원래 페이지 안의 여백은 유지됩니다.'),
    'slice_a4': ('긴 페이지 A4 나누기', '빈 가로 구간을 찾아 A4로 나눕니다. 안전한 분할점이 없는 큰 구간은 축소해 한 장에 보존합니다. 결과 글자 크기를 확인해 주세요.'),
    'auto_forms': ('입력 가능한 양식 만들기', '빈 사각형·밑줄·체크 칸을 PDF 입력 필드로 만듭니다. 어잉PDF의 양식 입력 또는 다른 양식 지원 뷰어에서 입력하세요. 감지 결과를 확인해 주세요. 스캔은 제외합니다.'),
    'bates': ('연속 식별번호·목차', '통일된 번호를 붙이고 클릭 가능한 목차 표지를 만듭니다. 기존 번호 가리기는 화면상의 흰 덮개이며 정보 삭제가 아닙니다.'),
    'stamp': ('도장·서명 찍기', '이미지의 흰 배경을 제거하고 지정한 페이지에 찍습니다. 300DPI 합치기를 선택하면 전체 PDF가 이미지로 바뀌어 검색·양식 입력이 사라집니다. 전자서명 인증 기능은 아닙니다.'),
    'replace_image': ('로고·이미지 일괄 교체', '선택한 이미지와 픽셀이 같은 이미지를 문서 전체에서 교체합니다. 위치와 회전은 유지하고 새 이미지는 비율을 유지해 맞춥니다. 벡터 로고·인라인 이미지는 제외합니다.'),
    'rotate': ('페이지 회전', '지정한 페이지를 90°, 180°, 270° 회전합니다.'),
    'auto_rotate': ('자동 방향 교정', '텍스트 방향을 분석해 돌아간 페이지를 자동으로 바로 세웁니다.'),
    'page_numbers': ('페이지 번호 넣기', '페이지 상단 또는 하단에 일련번호를 추가합니다.'),
    'scale_pages': ('페이지 크기 맞춤', '모든 페이지를 A4, A3, Letter, B5 등 표준 규격으로 맞춥니다.'),
    'insert_blank': ('빈 페이지 삽입', '지정한 위치에 빈 페이지를 추가합니다.'),
    'overlay_pdf': ('PDF 겹쳐 넣기', '배경이나 편지지·양식 PDF를 페이지 위나 아래에 겹칩니다.'),
    'split_size': ('용량 기준 분할', '지정한 MB 이하 크기가 되도록 PDF를 여러 파일로 나누어 ZIP 저장합니다.'),
    'extract_images': ('포함 이미지 추출', 'PDF 안에 들어있는 원본 이미지들을 추출해 ZIP으로 저장합니다.'),
    'pdf_to_html': ('HTML 내보내기', 'PDF 텍스트와 구성을 웹 페이지(HTML) 파일로 추출합니다.'),
    'pdf_to_json': ('JSON 내보내기', '페이지 텍스트, 크기, 목차, 메타데이터를 JSON으로 추출합니다.'),
    'pdf_to_xml': ('XML 내보내기', '문서 구조와 텍스트를 XML 파일로 추출합니다.'),
    'pdf_to_pdfa': ('보관용 PDF/A 저장', '폰트 정리와 활성 스크립트 제거로 장기 보관용 사본을 만듭니다.'),
    'permissions': ('문서 권한 변경', '인쇄, 복사, 수정, 주석 허용 권한을 세부 설정해 암호화합니다.'),
    'unlock_forms': ('양식 잠금 해제', '읽기 전용으로 잠긴 PDF 입력 칸을 다시 편집할 수 있게 풉니다.'),
    'attachments': ('첨부 파일 관리', 'PDF 내 첨부 파일을 ZIP으로 꺼내거나 추가·삭제합니다.'),
    'bookmarks': ('목차·책갈피 편집', '문서 목차를 직접 편집하거나 제목 글자 크기로 자동 생성합니다.'),
    'qr_stamp': ('QR 코드 스탬프', 'URL이나 안내 문구를 담은 QR 코드를 오프라인에서 생성해 찍습니다.'),
    'sanitize_scripts': ('활성 콘텐츠·스크립트 소독', 'PDF 내부의 JavaScript, 자동 실행 액션, 첨부 파일을 제거합니다.'),
}


def luhn(number):
    digits = [int(char) for char in number if char.isascii() and char.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    return sum((digit * 2 - 9 if digit > 4 else digit * 2) if index % 2 else digit
               for index, digit in enumerate(reversed(digits))) % 10 == 0


def sensitive_matches(text):
    patterns = (
        r'(?<!\d)\d{6}-[1-4]\d{6}(?!\d)',
        r'(?<!\w)[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\w)',
        r'(?<!\d)(?:\+82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)',
        r'(?<!\d)0[2-6]\d?[- .]\d{3,4}[- .]\d{4}(?!\d)',
        r'(?<!\d)(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?!\d)',
    )
    matches = {match.group() for pattern in patterns for match in re.finditer(pattern, text)}
    for match in re.finditer(r'(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)', text):
        if luhn(match.group()):
            matches.add(match.group())
    return matches


def content_bounds(page):
    bounds = pdf.Rect()
    for block in page.get_text('blocks'):
        if block[6] == 1 or block[4].strip():
            bounds |= pdf.Rect(block[:4])
    for item in page.get_image_info():
        bounds |= pdf.Rect(item['bbox'])
    for drawing in page.get_drawings():
        rect = pdf.Rect(drawing['rect'])
        # Thin vector lines still count as content.
        padding = max(float(drawing.get('width') or 0), 1)
        bounds |= rect + (-padding, -padding, padding, padding)
    for annotation in page.annots() or ():
        bounds |= annotation.rect
    for widget in page.widgets() or ():
        bounds |= widget.rect
    for link in page.get_links():
        if 'from' in link:
            bounds |= pdf.Rect(link['from']) * page.derotation_matrix
    return bounds


def transform(source, target, operation, password='', user_password='', owner_password='',
              allow_print=True, allow_copy=False, cancelled=lambda: False, progress=lambda value: None,
              watermark_text='', watermark_image='', watermark_opacity=.2, split_ranges='', group_size=1, target_mb=10,
              form_values=None, bates_prefix='', bates_start=1, bates_digits=6, bates_hide_old=True, bates_cover=False,
              stamp_pages='1', stamp_x_mm=10, stamp_y_mm=10, stamp_width_mm=30, stamp_flatten=True, replace_xref=0, replace_digest='', form_review=None,
              custom_terms='', redact_boxes=None, allow_best_effort=False, rotation=90, page_range='',
              number_position='bottom-center', number_start=1, paper_size='A4', insert_after=1, insert_count=1,
              overlay_path='', overlay_password='', overlay_foreground=True, max_mb=5.0,
              allow_edit=False, allow_annotate=False, attachment_mode='extract', attachment_path='',
              toc_text='', auto_toc=False, qr_text=''):
    if operation not in TOOLS and operation != 'fill_forms':
        raise ValueError(tr('지원하지 않는 PDF 도구입니다.'))
    source, target = Path(source).resolve(), Path(target).resolve()
    if target == source or target.exists():
        raise ValueError(tr('원본이나 기존 파일을 덮어쓸 수 없습니다. 새 파일명을 선택해 주세요.'))
    split_operation = operation in {'split_ranges', 'split_groups', 'split_toc', 'split_size'}
    archive_operation = split_operation or operation in {'svg', 'dxf', 'extract_images'} or (operation == 'attachments' and attachment_mode == 'extract')
    extension = (
        '.zip' if archive_operation
        else '.md' if operation == 'markdown'
        else '.html' if operation == 'pdf_to_html'
        else '.json' if operation == 'pdf_to_json'
        else '.xml' if operation == 'pdf_to_xml'
        else '.pdf'
    )
    if target.suffix.lower() != extension:
        raise ValueError(tr('저장 파일의 확장자는 {v0}여야 합니다.', v0=extension))
    if operation == 'encrypt':
        if not user_password or not owner_password:
            raise ValueError(tr('열기 암호와 소유자 암호를 모두 입력해 주세요.'))
        if user_password == owner_password:
            raise ValueError(tr('열기 암호와 소유자 암호를 다르게 설정해 주세요.'))
        if any(len(value.encode('utf-8')) > 40 for value in (user_password, owner_password)):
            raise ValueError(tr('암호는 UTF-8 기준 40바이트 이하로 입력해 주세요.'))
    elif operation == 'permissions':
        if not owner_password:
            raise ValueError(tr('권한 변경에는 소유자 암호가 필요합니다.'))
        if user_password and user_password == owner_password:
            raise ValueError(tr('열기 암호와 소유자 암호를 다르게 설정해 주세요.'))
        if any(len(value.encode('utf-8')) > 40 for value in (user_password, owner_password)):
            raise ValueError(tr('암호는 UTF-8 기준 40바이트 이하로 입력해 주세요.'))
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, scratch_name = tempfile.mkstemp(prefix='.eoing-', suffix=extension, dir=target.parent)
    os.close(handle)
    scratch = Path(scratch_name)
    changed = 0
    try:
        with open_pdf(source, password) as doc:
            blank = []
            count = len(doc)
            if operation == 'safe_submission':
                from .submission import prepare
                changed = prepare(doc, scratch, cancelled, progress)
            elif operation == 'replace_image':
                from .image_replace import apply
                changed = apply(doc, replace_xref, watermark_image, replace_digest, cancelled, progress)
            elif operation == 'stamp':
                from .stamping import apply
                changed = apply(doc, watermark_image, stamp_pages, stamp_x_mm, stamp_y_mm, stamp_width_mm, cancelled, progress)
                if stamp_flatten:
                    from .scan_pdf import render_copy
                    render_copy(doc, scratch, 'flatten', cancelled, lambda value: progress(45 + value // 2))
            elif operation == 'qr_stamp':
                from .extra_tools import add_qr_stamp
                changed = add_qr_stamp(doc, qr_text, stamp_pages, stamp_x_mm, stamp_y_mm, stamp_width_mm, cancelled, progress)
            elif operation == 'bates':
                from .bates import apply
                changed = apply(doc, bates_prefix, bates_start, bates_digits, bates_hide_old, bates_cover, cancelled, progress)
            elif operation == 'fill_forms':
                from .forms import fill_fields
                changed = fill_fields(doc, form_values, cancelled, progress)
            elif operation == 'unlock_forms':
                from .extra_tools import unlock_forms
                changed = unlock_forms(doc, cancelled, progress)
            elif operation == 'outlines':
                from .text_outlines import export
                changed = export(doc, scratch, cancelled, progress)
            elif operation == 'auto_forms':
                from .forms import create_fields
                changed = create_fields(doc, cancelled, progress, reviewed=form_review)
            elif operation == 'slice_a4':
                from .roll_layout import slice_a4
                changed = slice_a4(doc, scratch, cancelled, progress)
            elif operation == 'stitch':
                from .roll_layout import stitch
                changed = stitch(doc, scratch, cancelled, progress)
            elif operation == 'scale_pages':
                from .extra_tools import scale_pages
                changed = scale_pages(doc, scratch, paper_size, cancelled, progress)
            elif operation == 'insert_blank':
                from .extra_tools import insert_blank_pages
                changed = insert_blank_pages(doc, insert_after, insert_count, paper_size, cancelled, progress)
            elif operation == 'overlay_pdf':
                from .extra_tools import overlay_pdf
                changed = overlay_pdf(doc, overlay_path, overlay_password, overlay_foreground, cancelled, progress)
            elif operation == 'rotate':
                from .extra_tools import rotate_pages
                changed = rotate_pages(doc, rotation, page_range, cancelled, progress)
            elif operation == 'auto_rotate':
                from .extra_tools import auto_rotate_pages
                changed = auto_rotate_pages(doc, cancelled, progress)
            elif operation == 'page_numbers':
                from .extra_tools import add_page_numbers
                changed = add_page_numbers(doc, page_range, number_start, number_position, cancelled, progress)
            elif operation == 'bookmarks':
                from .extra_tools import edit_bookmarks
                changed = edit_bookmarks(doc, toc_text, auto_toc, cancelled, progress)
            elif operation == 'attachments':
                from .extra_tools import manage_attachments
                changed = manage_attachments(doc, scratch, attachment_mode, attachment_path, cancelled, progress)
            elif operation == 'extract_images':
                from .extra_tools import extract_images_zip
                changed = extract_images_zip(doc, scratch, cancelled, progress)
            elif operation == 'pdf_to_html':
                from .extra_tools import pdf_to_html
                changed = pdf_to_html(doc, scratch, source.name, cancelled, progress)
            elif operation == 'pdf_to_json':
                from .extra_tools import pdf_to_json
                changed = pdf_to_json(doc, scratch, source.name, cancelled, progress)
            elif operation == 'pdf_to_xml':
                from .extra_tools import pdf_to_xml
                changed = pdf_to_xml(doc, scratch, source.name, cancelled, progress)
            elif operation == 'pdf_to_pdfa':
                from .extra_tools import convert_to_pdfa
                changed = convert_to_pdfa(doc, scratch, cancelled, progress)
            elif operation == 'dxf':
                from .dxf_export import export
                changed = export(doc, scratch, cancelled, progress)
            elif operation == 'svg':
                from .svg_export import export
                changed = export(doc, scratch, cancelled, progress)
            elif operation in {'four_up', 'booklet'}:
                from .imposition import compose
                changed = compose(doc, scratch, operation, cancelled, progress)
            elif operation == 'markdown':
                from .markdown_export import export
                changed = export(doc, scratch, source.name, cancelled, progress)
            elif operation == 'repair':
                from .recovery import rebuild
                changed = rebuild(doc, scratch, cancelled, progress)
            elif operation == 'target_size':
                from .compression import compress
                compress(doc, scratch, target_mb, cancelled, progress, allow_best_effort=allow_best_effort)
                changed = len(doc)
            elif operation == 'split_size':
                from .extra_tools import split_by_size_zip
                changed = split_by_size_zip(doc, scratch, max_mb, cancelled, progress)
            elif split_operation:
                from .splitter import write_archive
                changed = write_archive(doc, scratch, operation, split_ranges, group_size, cancelled, progress)
            elif operation == 'reverse':
                from .page_edits import apply_page_order
                apply_page_order(doc, reversed(range(count)))
                changed = count
            elif operation in {'watermark_text', 'watermark_png'}:
                from .watermark import apply
                changed = apply(doc, text=watermark_text if operation == 'watermark_text' else '',
                                image_path=watermark_image if operation == 'watermark_png' else '',
                                opacity=watermark_opacity, cancelled=cancelled, progress=progress)
            elif operation in {'flatten', 'deskew', 'deskew_bw', 'smart_dark', 'print_light'}:
                from .scan_pdf import render_copy
                changed = render_copy(doc, scratch, operation, cancelled, progress)
            elif operation == 'sanitize_scripts':
                from .sanitize import sanitize_active_content
                changed = sanitize_active_content(doc, remove_scripts=True, remove_attachments=True, cancelled=cancelled, progress=progress)
            elif operation == 'split_spread':
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                doc.bake(annots=True, widgets=True)
                with pdf.open() as out:
                    for index, page in enumerate(doc):
                        if cancelled():
                            raise Cancelled(tr('작업을 취소했습니다.'))
                        rect = page.rect
                        rotation = page.rotation
                        page.set_rotation(0)
                        # Reframe the visible CropBox before splitting; remove_rotation
                        # can reset a non-default CropBox in the current MuPDF version.
                        with pdf.open() as normalized:
                            visible = normalized.new_page(width=rect.width, height=rect.height)
                            if page.get_contents():
                                visible.show_pdf_page(visible.rect, doc, index,
                                                      clip=page.rect, rotate=-rotation)
                            middle = rect.width / 2
                            for clip in (pdf.Rect(0, 0, middle, rect.height),
                                         pdf.Rect(middle, 0, rect.width, rect.height)):
                                new_page = out.new_page(width=clip.width, height=clip.height)
                                if visible.get_contents():
                                    new_page.show_pdf_page(new_page.rect, normalized, 0, clip=clip)
                        progress(int((index + 1) / count * 90))
                    out.save(scratch, garbage=4, deflate=True)
                    changed = len(out)
            elif operation in {'remove_blank', 'trim', 'redact', 'searchable', 'ocr_redact'}:
                terms = [term.strip() for term in re.split(r'[,\n]+', custom_terms or '') if term.strip()]
                boxes_by_page = {}
                for box_item in redact_boxes or ():
                    if isinstance(box_item, dict) and isinstance(box_item.get('page'), int) and len(box_item.get('rect', ())) == 4:
                        boxes_by_page.setdefault(box_item['page'], []).append(box_item['rect'])
                for index, page in enumerate(doc):
                    if cancelled():
                        raise Cancelled(tr('작업을 취소했습니다.'))
                    if operation in {'searchable', 'ocr_redact'}:
                        from .ocr import add_searchable_layer
                        recognized = add_searchable_layer(page, cancelled)
                        if operation == 'searchable':
                            changed += recognized
                            progress(int((index + 1) / count * 90))
                            continue
                    if operation in {'redact', 'ocr_redact'}:
                        rectangles = set()
                        for match in sensitive_matches(page.get_text()):
                            rectangles.update(tuple(rect) for rect in page.search_for(match))
                        for term in terms:
                            rectangles.update(tuple(rect) for rect in page.search_for(term))
                        for box in boxes_by_page.get(index, ()):
                            rectangles.add(tuple(float(v) for v in box))
                        for rect in rectangles:
                            page.add_redact_annot(pdf.Rect(rect), fill=(0, 0, 0))
                        if rectangles:
                            page.apply_redactions(images=2, graphics=0, text=0)
                            changed += len(rectangles)
                    else:
                        bounds = content_bounds(page)
                        if bounds.is_empty and not page.get_links():
                            blank.append(index)
                        elif operation == 'trim' and not bounds.is_empty:
                            # Extracted content is unrotated even when page.rect is rotated.
                            visible = pdf.Rect(0, 0, page.cropbox.width, page.cropbox.height)
                            crop = (bounds + (-12, -12, 12, 12)) & visible
                            # Text coordinates are relative to the visible crop origin.
                            crop += (page.cropbox.x0, page.cropbox.y0, page.cropbox.x0, page.cropbox.y0)
                            if not crop.is_empty:
                                page.set_cropbox(crop)
                                changed += 1
                    progress(int((index + 1) / count * 90))
                if operation == 'remove_blank' and blank:
                    if len(blank) == count:
                        raise ValueError(tr('모든 페이지가 비어 있습니다. 빈 PDF는 저장하지 않습니다.'))
                    doc.delete_pages(blank)
                    changed = len(blank)
            if operation in {'metadata', 'redact', 'ocr_redact'}:
                doc.set_metadata({})
                doc.del_xml_metadata()
                if operation == 'metadata':
                    from .sanitize import sanitize
                    sanitize(doc, cancelled, progress)
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            self_saved = {
                'safe_submission', 'split_spread', 'flatten', 'deskew', 'deskew_bw',
                'smart_dark', 'print_light', 'target_size', 'repair', 'markdown',
                'four_up', 'booklet', 'stitch', 'slice_a4', 'outlines', 'scale_pages',
                'pdf_to_html', 'pdf_to_json', 'pdf_to_xml', 'pdf_to_pdfa',
                'extract_images', 'split_size',
            }
            if not (operation == 'stamp' and stamp_flatten) and not archive_operation and operation not in self_saved:
                options = {'garbage': 4, 'deflate': True, 'encryption': pdf.PDF_ENCRYPT_NONE}
                if operation in {'encrypt', 'permissions'}:
                    permissions = pdf.PDF_PERM_ACCESSIBILITY
                    if allow_print:
                        permissions |= pdf.PDF_PERM_PRINT | pdf.PDF_PERM_PRINT_HQ
                    if allow_copy:
                        permissions |= pdf.PDF_PERM_COPY
                    if operation == 'permissions':
                        if allow_edit:
                            permissions |= pdf.PDF_PERM_MODIFY
                        if allow_annotate:
                            permissions |= pdf.PDF_PERM_ANNOTATE
                    options.update(encryption=pdf.PDF_ENCRYPT_AES_256, owner_pw=owner_password,
                                   user_pw=user_password, permissions=permissions)
                doc.save(scratch, **options)
        if archive_operation:
            with zipfile.ZipFile(scratch) as archive:
                if archive.testzip() is not None:
                    raise ValueError(tr('분할 파일 검증에 실패했습니다.'))
        elif operation not in {'markdown', 'pdf_to_html', 'pdf_to_json', 'pdf_to_xml'}:
            with open_pdf(scratch, user_password if operation in {'encrypt', 'permissions'} and user_password else ''):
                pass
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        if os.name == 'nt':
            os.rename(scratch, target)
        else:
            os.link(scratch, target)
        progress(100)
        return changed
    finally:
        scratch.unlink(missing_ok=True)
