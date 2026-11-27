"""Task-based discovery for PDF tools and the reader's everyday actions."""
from dataclasses import dataclass
import unicodedata

from .advanced import TOOLS
from .localization import tr


@dataclass(frozen=True)
class ToolCategory:
    key: str
    title: str
    description: str


@dataclass(frozen=True)
class ToolEntry:
    key: str
    title: str
    description: str
    category: str
    aliases: tuple[str, ...] = ()


CATEGORIES = (
    ToolCategory('edit', '직인·워터마크·양식', '직인, 서명, QR 스탬프, 워터마크, 양식과 목차를 다룹니다.'),
    ToolCategory('pages', '페이지 정리', '페이지 순서, 회전, 규격, 여백, 분할과 합치기를 처리합니다.'),
    ToolCategory('convert', '변환·내보내기', 'PDF와 이미지, HTML, Markdown, Office/한글 문서를 상호 변환합니다.'),
    ToolCategory('scan', '스캔·문자 인식', '스캔 보정, 자동 방향 교정과 OCR 검색을 처리합니다.'),
    ToolCategory('security', '보안·개인정보', '암호, 권한, 개인정보 삭제, 스크립트 소독과 첨부를 관리합니다.'),
    ToolCategory('view', '보기·발표·인쇄', '슬라이드쇼, 판서, 모아찍기와 인쇄용 사본을 준비합니다.'),
    ToolCategory('export', '복사·추출', '표, 이미지, 구조화 데이터를 파일이나 클립보드로 꺼냅니다.'),
    ToolCategory('optimize', '압축·복구·비교', '용량 최적화, 손상 복구, 문서 비교와 상세 검사를 수행합니다.'),
)

# Each transformation appears exactly once. Reader actions share this catalog
# so discovery does not depend on knowing which part of the window owns a tool.
_TRANSFORM_ENTRIES = (
    ('stamp', 'edit', '흰 배경을 없앤 직인을 직접 옮기고 크기를 조절합니다.', ('도장', '서명', 'seal', 'signature')),
    ('qr_stamp', 'edit', 'URL이나 텍스트 QR 코드를 생성해 문서에 찍습니다.', ('qr', '큐알', '스탬프', 'barcode')),
    ('watermark_text', 'edit', '문서에 반투명 문구를 넣습니다.', ('대외비', '워터마크', 'watermark')),
    ('watermark_png', 'edit', '투명 이미지를 워터마크로 넣습니다.', ('로고', '이미지', 'watermark')),
    ('auto_forms', 'edit', '빈 표와 밑줄을 입력 칸으로 바꿉니다.', ('입력란', '표 서식', 'fillable', 'form')),
    ('unlock_forms', 'edit', '읽기 전용으로 잠긴 입력 칸을 다시 편집 가능하게 풉니다.', ('양식 잠금', 'unlock', 'form')),
    ('bates', 'edit', '일련번호와 클릭 가능한 목차를 넣습니다.', ('페이지 번호', '연속 번호', 'bates')),
    ('bookmarks', 'edit', '문서 목차(책갈피)를 편집하거나 제목에서 자동 생성합니다.', ('목차', '책갈피', 'bookmark', 'toc')),
    ('replace_image', 'edit', '문서 안의 같은 로고·이미지를 한 번에 바꿉니다.', ('로고 교체', 'replace', 'image')),
    ('rotate', 'pages', '지정한 페이지를 90°, 180°, 270° 회전합니다.', ('회전', 'rotate', '방향')),
    ('auto_rotate', 'scan', '텍스트 방향을 분석해 돌아간 페이지를 자동으로 바로 세웁니다.', ('자동 회전', 'auto rotate', '방향')),
    ('page_numbers', 'pages', '페이지 상단 또는 하단에 페이지 번호를 추가합니다.', ('페이지 번호', 'page number', 'numbering')),
    ('scale_pages', 'pages', '모든 페이지를 A4, A3, Letter 등 표준 규격으로 맞춥니다.', ('용지 크기', 'a4', 'scale', 'resize')),
    ('insert_blank', 'pages', '지정한 위치에 빈 페이지를 추가합니다.', ('빈 페이지', 'blank', 'insert')),
    ('overlay_pdf', 'pages', '다른 PDF를 배경이나 전경에 겹쳐서 합성합니다.', ('겹치기', '편지지', 'overlay')),
    ('reverse', 'pages', '마지막 페이지부터 순서를 뒤집습니다.', ('순서', '역순', 'reverse')),
    ('remove_blank', 'pages', '내용이 없는 빈 페이지만 제거합니다.', ('삭제', 'blank')),
    ('trim', 'pages', '본문 바깥의 여백을 줄입니다.', ('자르기', 'crop', 'trim')),
    ('split_spread', 'pages', '책을 펼쳐 스캔한 양쪽 면을 나눕니다.', ('책 스캔', '분할', 'spread')),
    ('split_ranges', 'pages', '지정한 페이지 범위별로 파일을 나눕니다.', ('추출', '분할', 'split')),
    ('split_groups', 'pages', '지정한 페이지 수씩 파일을 나눕니다.', ('분할', 'split')),
    ('split_size', 'pages', '지정한 MB 이하 크기가 되도록 자동으로 나누어 저장합니다.', ('용량 분할', '분할', 'split size')),
    ('split_toc', 'pages', '목차의 시작 페이지를 기준으로 나눕니다.', ('책갈피', '분할', 'bookmark')),
    ('stitch', 'pages', '여러 페이지를 세로로 길게 이어 붙입니다.', ('연결', '병합', 'stitch')),
    ('slice_a4', 'pages', '긴 문서를 A4 크기의 페이지로 나눕니다.', ('분할', 'a4', 'slice')),
    ('deskew', 'scan', '기울어진 스캔을 수평으로 보정합니다.', ('회전', '기울기', 'deskew')),
    ('deskew_bw', 'scan', '기울기를 바로잡고 흑백으로 선명하게 만듭니다.', ('흑백', '보정', 'black white')),
    ('searchable', 'scan', '스캔 속 글자를 인식해 검색할 수 있게 만듭니다.', ('ocr', '텍스트', '검색')),
    ('safe_submission', 'scan', '증빙 스캔을 보정하고 인식한 개인정보를 지웁니다.', ('제출', '종이 그림자', 'ocr')),
    ('ocr_redact', 'scan', '스캔 속 개인정보를 인식해 실제로 삭제합니다.', ('보안', '마스킹', 'ocr', 'redact')),
    ('encrypt', 'security', '열기 암호와 소유자 암호를 설정합니다.', ('비밀번호', '잠금', 'encrypt')),
    ('decrypt', 'security', '암호를 알고 있는 문서의 잠금을 해제합니다.', ('비밀번호', '잠금', 'decrypt')),
    ('permissions', 'security', '인쇄·복사·수정·주석 권한을 세부 설정합니다.', ('권한', 'permission', '보호')),
    ('redact', 'security', '개인정보와 지정한 단어를 찾아 영구 삭제합니다.', ('가리기', '마스킹', 'redact')),
    ('metadata', 'security', '문서 정보와 발견 가능한 추적 흔적을 지웁니다.', ('속성', '메타데이터', '추적점', 'metadata')),
    ('sanitize_scripts', 'security', 'JavaScript, 자동 실행 액션과 첨부 파일을 제거합니다.', ('소독', 'sanitize', '스크립트', 'javascript')),
    ('attachments', 'security', 'PDF에 포함된 첨부 파일을 꺼내거나 추가·삭제합니다.', ('첨부', 'attachment', 'embedded')),
    ('smart_dark', 'view', '어두운 배경의 읽기용 이미지 사본을 만듭니다.', ('다크 모드', 'dark')),
    ('print_light', 'view', '어두운 페이지를 밝은 인쇄용 사본으로 바꿉니다.', ('반전', '인쇄', 'print')),
    ('flatten', 'view', '주석과 양식을 포함해 이미지 PDF로 합칩니다.', ('평탄화', '300dpi', 'flatten')),
    ('four_up', 'view', 'A4 한 면에 네 페이지를 배치합니다.', ('인쇄', '모아찍기', '4up')),
    ('booklet', 'view', '양면으로 접어 읽을 소책자 순서를 만듭니다.', ('인쇄', '책자', 'booklet')),
    ('outlines', 'view', '글자를 벡터 도형으로 바꾼 인쇄용 사본을 만듭니다.', ('글꼴', '인쇄', 'outline')),
    ('pdf_to_pdfa', 'convert', '폰트와 구조를 정리한 장기 보관용 PDF/A 사본을 만듭니다.', ('보관', 'pdfa', 'pdf/a')),
    ('pdf_to_html', 'convert', 'PDF를 웹 브라우저에서 볼 수 있는 HTML로 내보냅니다.', ('웹', 'html', '변환')),
    ('pdf_to_json', 'export', '페이지 텍스트와 메타데이터를 JSON으로 추출합니다.', ('json', '데이터')),
    ('pdf_to_xml', 'export', '문서 구조와 텍스트를 XML 파일로 추출합니다.', ('xml', '데이터')),
    ('extract_images', 'export', 'PDF 안의 원본 이미지를 전부 추출해 ZIP으로 저장합니다.', ('이미지 추출', 'extract image')),
    ('markdown', 'export', '제목·본문·표를 Markdown 문서로 꺼냅니다.', ('텍스트', 'md', 'markdown')),
    ('dxf', 'export', '도형 경로를 CAD 파일로 꺼냅니다.', ('캐드', 'cad', 'dxf')),
    ('svg', 'export', '페이지를 벡터 이미지로 꺼냅니다.', ('벡터', 'svg')),
    ('target_size', 'optimize', '목표 파일 크기에 맞춰 이미지 용량을 줄입니다.', ('압축', '크기', '용량', 'compress')),
    ('repair', 'optimize', '읽을 수 있는 내용을 유지하며 PDF 구조를 복구합니다.', ('오류', '손상', 'repair')),
)

_READER_ENTRIES = (
    ToolEntry('presentation', '슬라이드쇼 · F5', '전체 화면으로 발표하고 화면에 판서합니다.', 'view', ('발표', '프레젠테이션', '판서', 'slideshow')),
    ToolEntry('save_as', '다른 이름으로 저장 · 형식 변환', '파일명과 확장자(PDF, PNG, JPG, TXT, HTML, MD 등)를 골라 저장합니다.', 'convert', ('저장', '다른이름', '내보내기', 'save as', 'export')),
    ToolEntry('multi_tool', '페이지 멀티툴 편집기', '큰 썸네일 보드에서 회전·재배치·삭제·삽입·추출을 한 번에 처리합니다.', 'pages', ('멀티툴', '페이지 편집', 'multi tool', 'reorder')),
    ToolEntry('merge', '여러 문서 합치기', 'PDF, 이미지, Office, 한글 문서를 하나로 합칩니다.', 'pages', ('병합', '합치기', 'merge', 'combine')),
    ToolEntry('convert_to_pdf', '문서·웹→PDF 변환', 'Word, Excel, PPT, 한글, HTML, Markdown, 텍스트를 PDF로 변환합니다.', 'convert', ('변환', 'office', 'hwp', 'html', 'convert')),
    ToolEntry('images_to_pdf', '이미지 묶어 PDF 만들기', 'JPG, PNG, WEBP 이미지를 하나의 PDF로 묶습니다.', 'convert', ('사진', '이미지', 'jpg', 'png')),
    ToolEntry('pdf_to_images', 'PDF → 이미지(PNG/JPG)', '페이지를 이미지 ZIP 또는 한 장의 긴 이미지로 저장합니다.', 'convert', ('png', 'jpg', '긴 이미지', 'image')),
    ToolEntry('pdf_to_text', 'PDF → 텍스트 추출', '본문 텍스트를 UTF-8 TXT 파일로 저장합니다.', 'convert', ('txt', '텍스트', '추출')),
    ToolEntry('form', '양식 입력', '현재 PDF의 입력 칸에 내용을 작성합니다.', 'edit', ('입력란', '표 서식', 'fill form')),
    ToolEntry('sign_draw', '서명 직접 그리기·만들기', '마우스로 서명을 그리거나 글자 서명을 만들어 바로 찍습니다.', 'edit', ('사인', '서명', 'draw', 'signature')),
    ToolEntry('annotate', '문서 위 주석·텍스트 쓰기', '열린 PDF 위에 텍스트, 형광펜, 펜, 도형을 추가합니다.', 'edit', ('주석', '메모', '형광펜', 'annotate')),
    ToolEntry('table', '표 드래그 복사', '표 영역을 선택해 엑셀에 붙여 넣습니다.', 'export', ('엑셀', '표 추출', 'excel', 'table')),
    ToolEntry('copy_image', '페이지 이미지 복사', '현재 페이지를 이미지로 클립보드에 복사합니다.', 'export', ('캡처', '그림', 'clipboard', 'image')),
    ToolEntry('viewmode', '페이지 목록 보기 전환', '페이지 목록의 축소판과 목록 보기를 바꿉니다.', 'view', ('사이드바', '썸네일', 'thumbnail')),
    ToolEntry('compare_docs', '두 문서 비교 (시각·텍스트)', '두 PDF의 시각적 차이와 텍스트 변경 내역을 함께 비교합니다.', 'optimize', ('비교', 'diff', 'compare')),
    ToolEntry('search_docs', '폴더 내 문서 내용 검색', '폴더 안 여러 PDF에서 문장과 단어를 검색합니다.', 'scan', ('검색', 'search', '폴더')),
    ToolEntry('summary', '핵심문장 요약', '오프라인으로 문서의 핵심 문장을 발췌 요약합니다.', 'optimize', ('요약', 'summary')),
    ToolEntry('pdf_info', 'PDF 상세 정보·규격 검사', '버전, 페이지 크기 혼재, 폰트 임베딩, 보안·JS 여부를 확인합니다.', 'optimize', ('정보', '검사', 'info', 'inspect')),
    ToolEntry('pipeline', '자동화 파이프라인 실행', '여러 PDF 도구를 순서대로 묶어 한 번에 실행합니다.', 'optimize', ('자동화', '파이프라인', 'processor', 'pipeline')),
)

ENTRIES = tuple(ToolEntry(key, TOOLS[key][0], description, category, aliases)
                for key, category, description, aliases in _TRANSFORM_ENTRIES) + _READER_ENTRIES
BY_KEY = {entry.key: entry for entry in ENTRIES}
RECOMMENDED = ('presentation', 'stamp', 'save_as', 'multi_tool', 'merge', 'watermark_text', 'searchable', 'target_size')


def normalize_search(text):
    return ' '.join(unicodedata.normalize('NFKC', str(text)).casefold().split())


def find_tools(query='', category='all', allowed_keys=None):
    """Match every search word against both Korean and localized tool terms."""
    categories = {item.key: item for item in CATEGORIES}
    normalized = normalize_search(query)
    terms = normalized.split()
    matches = []
    entries = [BY_KEY[key] for key in RECOMMENDED] if category == 'recommended' else ENTRIES
    allowed = set(allowed_keys) if allowed_keys is not None else None
    for entry in entries:
        if allowed is not None and entry.key not in allowed:
            continue
        if category not in ('all', 'recommended', entry.category):
            continue
        group = categories[entry.category]
        haystack = normalize_search(' '.join((entry.title, tr(entry.title),
            entry.description, tr(entry.description), *entry.aliases)))
        # A full category title remains searchable, but a single feature such
        # as "watermark" must not match unrelated tools in the same category.
        category_match = normalized in (normalize_search(group.title),
                                        normalize_search(tr(group.title)))
        if category_match or all(term in haystack for term in terms):
            matches.append(entry)
    return matches
