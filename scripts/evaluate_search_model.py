"""Run real Korean paraphrase retrieval and process memory measurements offline."""
import json
import os
from pathlib import Path
import time
import argparse
import sys
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import numpy as np
import psutil
import tempfile
import shutil
import subprocess

CASES = [
    ('직원이 휴가를 사용하려면 팀장의 승인을 받고 인사 시스템에 연차를 신청해야 합니다.', '쉬는 날을 신청하는 절차는?'),
    ('출장 교통비와 숙박비는 영수증을 첨부하여 재무팀에 청구하면 지급됩니다.', '업무 때문에 여행하며 쓴 돈을 돌려받으려면?'),
    ('비밀번호를 잊은 경우 로그인 화면에서 암호 재설정을 선택하고 이메일 인증을 진행합니다.', '계정에 들어갈 암호가 기억나지 않습니다.'),
    ('고객의 개인정보는 계약 종료 후 삼십 일 이내에 복구할 수 없도록 영구 삭제합니다.', '서비스 해지 뒤 고객 자료는 언제 파기하나요?'),
    ('화재 발생 시 엘리베이터를 사용하지 말고 계단을 통해 건물 밖 집결 장소로 대피합니다.', '건물에 불이 나면 어디로 나가야 하나요?'),
    ('제품 구매 후 칠 일 이내에는 미사용 상품을 반품하고 결제 금액을 환불받을 수 있습니다.', '산 물건이 필요 없어졌는데 돈을 돌려받을 수 있나요?'),
    ('매출액은 지난 분기 대비 이십 퍼센트 증가했으며 영업 이익도 크게 개선되었습니다.', '회사가 벌어들인 수입과 수익성은 어떻게 달라졌나요?'),
    ('이 프로그램은 인터넷 연결 없이 컴퓨터 안에서 문서를 처리하며 외부 서버로 전송하지 않습니다.', '문서를 온라인에 올리지 않고 사용할 수 있나요?'),
    ('신입 사원은 입사 첫날 노트북을 지급받고 정보 보안 교육을 이수해야 합니다.', '새로 취직한 직원이 처음 해야 하는 일은?'),
    ('배터리 수명을 늘리려면 장기간 보관 시 충전량을 절반 정도로 유지하고 고온을 피하십시오.', '전지를 오래 쓰려면 어떻게 보관해야 하나요?'),
]


def make_fixture(folder):
    import pymupdf as pdf
    folder = Path(folder)
    sample = folder / 'document-0.pdf'
    with pdf.open() as document:
        for text, _ in CASES:
            page = document.new_page()
            page.insert_font(fontname='korean', fontfile=str(Path(__file__).resolve().parents[1] / 'assets/fonts/Pretendard-Regular.ttf'))
            page.insert_text((40, 80), text, fontname='korean', fontsize=10)
        document.save(sample)
    for index in range(1, 30):
        shutil.copyfile(sample, folder / f'document-{index}.pdf')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--external', action='store_true')
    parser.add_argument('--pdf-index', action='store_true')
    parser.add_argument('--make-fixture')
    args = parser.parse_args()
    if args.make_fixture:
        make_fixture(args.make_fixture)
        return
    folder = Path(__file__).resolve().parents[1] / 'temp/search-model'
    if args.external:
        folder /= 'external'
    started = time.perf_counter()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from eoingpdf.semantic_search import LocalEmbedder
    embedder = LocalEmbedder(folder)
    initialization_ms = (time.perf_counter() - started) * 1000
    encode = embedder.encode
    documents = np.array([encode(document) for document, query in CASES])
    matches = []
    times = []
    for index, (_, query) in enumerate(CASES):
        started = time.perf_counter()
        scores = documents @ encode(query)
        ranking = np.argsort(-scores)
        times.append((time.perf_counter() - started) * 1000)
        matches.append(dict(expected=index, actual=int(ranking[0]),
                            rank=int(np.where(ranking == index)[0][0]) + 1,
                            score=float(scores[ranking[0]])))
    index_metrics = None
    if args.pdf_index:
        from eoingpdf.semantic_search import PdfSearchIndex
        with tempfile.TemporaryDirectory(prefix='search-benchmark-') as temporary:
            temporary = Path(temporary)
            documents_folder = temporary / 'documents'
            documents_folder.mkdir()
            subprocess.run([sys.executable, str(Path(__file__).resolve()), '--make-fixture', str(documents_folder)],
                           check=True, timeout=30, capture_output=True)
            index = PdfSearchIndex(temporary / 'search.db', embedder)
            started = time.perf_counter()
            status = index.build(documents_folder)
            build_ms = (time.perf_counter() - started) * 1000
            durations = []
            for _, query in CASES:
                started = time.perf_counter()
                index.search(query)
                durations.append((time.perf_counter() - started) * 1000)
            index_metrics = dict(files=status['files'], pages=300, build_ms=build_ms,
                                 search_median_ms=float(np.median(durations)))
    memory = psutil.Process().memory_info()
    result = dict(model='static-similarity-mrl-multilingual-v1-256-int8',
                  cases=matches, top1=sum(row['rank'] == 1 for row in matches),
                  count=len(CASES), initialization_ms=initialization_ms,
                  query_median_ms=float(np.median(times)), rss_bytes=memory.rss,
                  peak_rss_bytes=getattr(memory, 'peak_wset', memory.rss),
                  private_bytes=getattr(memory, 'private', None))
    result['pdf_index'] = index_metrics
    (folder / ('evaluation-pdf.json' if args.pdf_index else 'evaluation.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
