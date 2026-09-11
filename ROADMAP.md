# 개발 현황

## 1차 MVP
- 구현: 우클릭 전체 선택을 받는 COM 연결 프로그램, 작은 자동 진행창
- 완료: PDF/이미지/텍스트 혼합 변환·병합, 핵심문장 발췌 요약
- 완료: 페이지 정리·회전·최적화·PNG·텍스트·페이지 번호
- 완료: Pretendard UI, 원본 보호, 이름 충돌 처리, 중단
- 검증 통과: DOCX/XLSX/PPTX 실제 Office 변환, 포터블 화면 실행
- 검증 통과: 탐색기 실제 우클릭 병합, HWP/HWPX 및 DOC/RTF/XLS/XLSM/PPT/PPTM 변환. `docs/VALIDATION.md` 참조
- 완료: 최종 패키지 메뉴 정리/재등록, 우클릭 HWP 변환/요약 검증, GitHub 저장소 재생성

## 2차 개선
- 예정: Windows 11 기본 우클릭 메뉴의 MSIX/IExplorerCommand 통합
- 예정: 문서 목록에서 결과별 재시도, 자주 쓰는 저장 위치
- 검증 통과: Windows 내장 한국어 OCR을 통한 스캔 PDF 텍스트 추출 및 요약

## 3차 확장
- 예정: 사용자가 연결하는 로컬 LLM 기반 생성형 요약
- 보류: 외부 AI 전송, 서버 연동, 광고, 로그인

## 완료 기준
형식별 실제 지원 범위는 `docs/VALIDATION.md`에 테스트 결과로 기록한다.
