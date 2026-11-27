"""Sequential multi-step PDF automation pipelines (local PDF Processor)."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from .advanced import TOOLS, transform
from .core import Cancelled
from .localization import tr

DEFAULT_PIPELINES = (
    {
        'id': 'preset-scan-submit',
        'name': '스캔 제출본 완성',
        'description': '기울기 보정 → 검색 가능한 PDF(OCR) → 10MB 이하 압축 → 메타데이터 소독',
        'steps': [
            {'operation': 'deskew', 'options': {}},
            {'operation': 'searchable', 'options': {}},
            {'operation': 'target_size', 'options': {'target_mb': 10.0, 'allow_best_effort': True}},
            {'operation': 'metadata', 'options': {}},
        ],
    },
    {
        'id': 'preset-privacy-safe',
        'name': '개인정보 안전 공개본',
        'description': '텍스트 개인정보 지우기 → 메타데이터·스크립트 소독 → 300DPI 이미지 평탄화',
        'steps': [
            {'operation': 'redact', 'options': {}},
            {'operation': 'metadata', 'options': {}},
            {'operation': 'flatten', 'options': {}},
        ],
    },
    {
        'id': 'preset-lightweight',
        'name': '대용량 문서 경량화',
        'description': '빈 페이지 제거 → 여백 자르기 → 10MB 이하 압축',
        'steps': [
            {'operation': 'remove_blank', 'options': {}},
            {'operation': 'trim', 'options': {}},
            {'operation': 'target_size', 'options': {'target_mb': 10.0, 'allow_best_effort': True}},
        ],
    },
    {
        'id': 'preset-print-handout',
        'name': '인쇄·배포용 정리',
        'description': '페이지 번호 넣기 → 밝은 인쇄용 사본 → 4쪽 모아찍기',
        'steps': [
            {'operation': 'page_numbers', 'options': {}},
            {'operation': 'print_light', 'options': {}},
            {'operation': 'four_up', 'options': {}},
        ],
    },
)

NON_PDF_FINAL_OPS = frozenset({'split_ranges', 'split_groups', 'split_toc', 'split_size', 'svg', 'dxf', 'markdown', 'pdf_to_html', 'pdf_to_json', 'pdf_to_xml', 'extract_images'})


def pipelines_path() -> Path:
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'EoingPDF'
    return base / 'pipelines.json'


def load_custom_pipelines() -> list[dict]:
    path = pipelines_path()
    try:
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            return []
        valid = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get('name'), str) and isinstance(item.get('steps'), list):
                valid.append(item)
        return valid
    except (OSError, ValueError):
        return []


def save_custom_pipelines(items: list[dict]) -> Path:
    path = pipelines_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def expected_extension(operation: str) -> str:
    if operation in {'split_ranges', 'split_groups', 'split_toc', 'split_size', 'svg', 'dxf', 'extract_images'}:
        return '.zip'
    if operation == 'markdown':
        return '.md'
    if operation == 'pdf_to_html':
        return '.html'
    if operation == 'pdf_to_json':
        return '.json'
    if operation == 'pdf_to_xml':
        return '.xml'
    return '.pdf'


def run_pipeline(source: str | Path, target: str | Path, steps: list[dict], password: str = '',
                 cancelled=lambda: False, progress=lambda value, message='': None) -> int:
    if not steps:
        raise ValueError(tr('파이프라인에 실행할 도구를 한 개 이상 추가해 주세요.'))
    for idx, step in enumerate(steps):
        op = step.get('operation', '')
        if op not in TOOLS:
            raise ValueError(tr('파이프라인의 지원하지 않는 도구입니다: {op}', op=op))
        if idx < len(steps) - 1 and op in NON_PDF_FINAL_OPS:
            raise ValueError(tr('{tool} 도구는 PDF가 아닌 파일을 출력하므로 마지막 단계에만 둘 수 있습니다.', tool=tr(TOOLS[op][0])))

    source = Path(source).resolve()
    target = Path(target).resolve()
    if source == target or target.exists():
        raise ValueError(tr('원본이나 기존 파일을 덮어쓸 수 없습니다. 새 파일명을 선택해 주세요.'))

    final_ext = expected_extension(steps[-1]['operation'])
    if target.suffix.lower() != final_ext:
        raise ValueError(tr('저장 파일의 확장자는 {v0}여야 합니다.', v0=final_ext))

    target.parent.mkdir(parents=True, exist_ok=True)
    total_steps = len(steps)
    total_changes = 0
    with tempfile.TemporaryDirectory(prefix='.eoing-pipe-', dir=target.parent) as temp_dir:
        temp_root = Path(temp_dir)
        current_input = source
        current_password = password
        for index, step in enumerate(steps):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            op = step['operation']
            opts = dict(step.get('options') or {})
            step_ext = expected_extension(op)
            step_out = temp_root / f'step_{index + 1:02d}{step_ext}'
            step_title = tr(TOOLS[op][0])

            def step_progress(pct: int, idx=index, name=step_title):
                overall = int(((idx + pct / 100.0) / total_steps) * 95)
                progress(overall, f'[{idx + 1}/{total_steps}] {name}')

            step_progress(0)
            total_changes += transform(
                current_input,
                step_out,
                op,
                password=current_password,
                cancelled=cancelled,
                progress=step_progress,
                **opts,
            )
            current_input = step_out
            current_password = opts.get('user_password', '') if op == 'encrypt' else ''
        if cancelled():
            raise Cancelled(tr('작업을 취소했습니다.'))
        shutil.move(str(current_input), str(target))
    progress(100, tr('파이프라인 완료'))
    return total_changes
