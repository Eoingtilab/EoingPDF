"""Deterministic extractive summaries, with page provenance and no network."""
from .localization import tr
from collections import Counter
import math
import re
from .core import open_pdf, Cancelled
from .ocr import page_text

STOP = {'그리고', '그러나', '대한', '위한', '있는', '합니다', '있습니다', '에서', '으로', 'the', 'and', 'that', 'with', 'this', 'from', 'have', 'will'}


def summarize(path, cancelled=lambda: False, limit=7):
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError(tr('요약 문장 수는 1~20 사이여야 합니다.'))
    sentences = []
    ocr_pages = set()
    with open_pdf(path) as doc:
        count = doc.page_count
        for index, page in enumerate(doc):
            if cancelled():
                raise Cancelled(tr('작업을 취소했습니다.'))
            text, used_ocr = page_text(page, cancelled)
            if used_ocr:
                ocr_pages.add(index + 1)
            for sentence in re.split(r'(?<=[.!?。])\s+|\n+', text):
                if cancelled():
                    raise Cancelled(tr('작업을 취소했습니다.'))
                sentence = sentence.strip()
                if len(sentence) > 2000:
                    sentence = sentence[:2000].rstrip() + '…'
                if len(sentence) >= 18:
                    words = [w.lower() for w in re.findall(r'[가-힣A-Za-z0-9]{2,}', sentence) if w.lower() not in STOP]
                    if words:
                        sentences.append((index + 1, sentence, words))
            if len(sentences) > 50000:
                raise ValueError(tr('요약할 문장이 너무 많습니다. 문서를 나눠 주세요.'))
    if not sentences:
        raise ValueError(tr('요약할 문장이 부족합니다. 글자가 선명한 문서를 선택해 주세요.'))
    frequency = Counter(w for _, _, words in sentences for w in set(words))
    ranked = sorted(
        range(len(sentences)),
        key=lambda i: sum(math.log1p(frequency[w]) for w in set(sentences[i][2])) / math.sqrt(len(sentences[i][2])),
        reverse=True,
    )
    selected, seen = [], set()
    for index in ranked:
        normalized = re.sub(r'\s+', '', sentences[index][1])
        if normalized not in seen:
            selected.append(index)
            seen.add(normalized)
        if len(selected) == limit:
            break
    lines = [tr('전체 {count}페이지 · 핵심문장 {sentences}개', count=count, sentences=len(selected)),
             tr('문장 빈도 기반 발췌입니다. 생성형 AI 요약이 아니며 원문 맥락을 확인해 주세요.'), '']
    if ocr_pages:
        lines.append(tr('OCR 사용 페이지: {pages}. 인식 오류가 있을 수 있으니 원문을 확인해 주세요.',
                        pages=', '.join(map(str, sorted(ocr_pages)))))
    for index in sorted(selected):
        page, sentence, _ = sentences[index]
        lines.append(f'[p.{page}] {sentence}')
    return '\n\n'.join(lines)
