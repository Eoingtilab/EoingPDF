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
    ToolCategory('edit', '직인·워터마크·양식', '직인과 문구를 넣고 양식을 입력합니다.'),
    ToolCategory('pages', '페이지 정리', '페이지 순서·여백·분할을 정리합니다.'),
    ToolCategory('scan', '스캔·문자 인식', '스캔을 보정하고 검색할 수 있게 만듭니다.'),
    ToolCategory('security', '보안·개인정보', '암호와 개인정보를 관리합니다.'),
    ToolCategory('view', '보기·발표·인쇄', '문서를 보고 발표와 인쇄를 준비합니다.'),
    ToolCategory('export', '복사·내보내기', '표·이미지·문서를 다른 형식으로 꺼냅니다.'),
    ToolCategory('optimize', '압축·복구', '파일 크기를 줄이고 손상을 복구합니다.'),
)

# Each transformation appears exactly once. Reader actions share this catalog
# so discovery does not depend on knowing which part of the window owns a tool.
_TRANSFORM_ENTRIES = (
    ('stamp', 'edit', '흰 배경을 없앤 직인을 직접 옮기고 크기를 조절합니다.', ('도장', '서명', 'seal', 'signature')),
    ('watermark_text', 'edit', '문서에 반투명 문구를 넣습니다.', ('대외비', '워터마크', 'watermark')),
    ('watermark_png', 'edit', '투명 이미지를 워터마크로 넣습니다.', ('로고', '이미지', 'watermark')),
    ('auto_forms', 'edit', '빈 표와 밑줄을 입력 칸으로 바꿉니다.', ('입력란', '표 서식', 'fillable', 'form')),
    ('bates', 'edit', '일련번호와 클릭 가능한 목차를 넣습니다.', ('페이지 번호', '연속 번호', 'bates')),
    ('replace_image', 'edit', '문서 안의 같은 로고·이미지를 한 번에 바꿉니다.', ('로고 교체', 'replace', 'image')),
    ('reverse', 'pages', '마지막 페이지부터 순서를 뒤집습니다.', ('순서', '역순', 'reverse')),
    ('remove_blank', 'pages', '내용이 없는 빈 페이지만 제거합니다.', ('삭제', 'blank')),
    ('trim', 'pages', '본문 바깥의 여백을 줄입니다.', ('자르기', 'crop', 'trim')),
    ('split_spread', 'pages', '책을 펼쳐 스캔한 양쪽 면을 나눕니다.', ('책 스캔', '분할', 'spread')),
    ('split_ranges', 'pages', '지정한 페이지 범위별로 파일을 나눕니다.', ('추출', '분할', 'split')),
    ('split_groups', 'pages', '지정한 페이지 수씩 파일을 나눕니다.', ('분할', 'split')),
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
    ('redact', 'security', '텍스트 속 개인정보를 찾아 실제로 삭제합니다.', ('가리기', '마스킹', 'redact')),
    ('metadata', 'security', '문서 정보와 발견 가능한 추적 흔적을 지웁니다.', ('속성', '메타데이터', '추적점', 'metadata')),
    ('smart_dark', 'view', '어두운 배경의 읽기용 이미지 사본을 만듭니다.', ('다크 모드', 'dark')),
    ('print_light', 'view', '어두운 페이지를 밝은 인쇄용 사본으로 바꿉니다.', ('반전', '인쇄', 'print')),
    ('flatten', 'view', '주석과 양식을 포함해 이미지 PDF로 합칩니다.', ('평탄화', '300dpi', 'flatten')),
    ('four_up', 'view', 'A4 한 면에 네 페이지를 배치합니다.', ('인쇄', '모아찍기', '4up')),
    ('booklet', 'view', '양면으로 접어 읽을 소책자 순서를 만듭니다.', ('인쇄', '책자', 'booklet')),
    ('outlines', 'view', '글자를 벡터 도형으로 바꾼 인쇄용 사본을 만듭니다.', ('글꼴', '인쇄', 'outline')),
    ('markdown', 'export', '제목·본문·표를 Markdown 문서로 꺼냅니다.', ('텍스트', 'md', 'markdown')),
    ('dxf', 'export', '도형 경로를 CAD 파일로 꺼냅니다.', ('캐드', 'cad', 'dxf')),
    ('svg', 'export', '페이지를 벡터 이미지로 꺼냅니다.', ('벡터', 'svg')),
    ('target_size', 'optimize', '목표 파일 크기에 맞춰 이미지 용량을 줄입니다.', ('압축', '크기', '용량', 'compress')),
    ('repair', 'optimize', '읽을 수 있는 내용을 유지하며 PDF 구조를 복구합니다.', ('오류', '손상', 'repair')),
)

_READER_ENTRIES = (
    ToolEntry('presentation', '슬라이드쇼 · F5', '전체 화면으로 발표하고 화면에 판서합니다.', 'view', ('발표', '프레젠테이션', '판서', 'slideshow')),
    ToolEntry('form', '양식 입력', '현재 PDF의 입력 칸에 내용을 작성합니다.', 'edit', ('입력란', '표 서식', 'fill form')),
    ToolEntry('table', '표 드래그 복사', '표 영역을 선택해 엑셀에 붙여 넣습니다.', 'export', ('엑셀', '표 추출', 'excel', 'table')),
    ToolEntry('copy_image', '페이지 이미지 복사', '현재 페이지를 이미지로 클립보드에 복사합니다.', 'export', ('캡처', '그림', 'clipboard', 'image')),
    ToolEntry('viewmode', '페이지 목록 보기 전환', '왼쪽 페이지 목록의 축소판과 목록 보기를 바꿉니다.', 'view', ('사이드바', '썸네일', 'thumbnail')),
)

ENTRIES = tuple(ToolEntry(key, TOOLS[key][0], description, category, aliases)
                for key, category, description, aliases in _TRANSFORM_ENTRIES) + _READER_ENTRIES
BY_KEY = {entry.key: entry for entry in ENTRIES}
RECOMMENDED = ('presentation', 'stamp', 'form', 'watermark_text', 'searchable', 'target_size')


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
