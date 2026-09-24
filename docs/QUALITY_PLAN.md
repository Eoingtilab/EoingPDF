# 어잉PDF 정식 버전 품질 검증 계획

전체 요구 기준은 `MASTER_SPEC_V2.md`와 사용자의 추가 실행 지시입니다. 일부 테스트 통과를 전체 완료로 대체하지 않습니다.
최초 인증 후 오프라인 사용 허용은 사용자가 확정한 변경 사항입니다.

## 기준과 적용 범위

[ISO/IEC/IEEE 29119-2:2021](https://www.iso.org/standard/79428.html)의 테스트 프로세스 관점으로 계획·설계·실행·결함·종료 증적을 관리합니다.
[ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html)의 제품 품질 모델을 품질 검토 틀로 사용합니다.
현재 공식 인증이나 표준 전체 조항 준수를 주장하지 않습니다. 표준 원문 전체에 대한 독립 적합성 심사는 별개입니다.

## 테스트 관리

1. 요구사항과 변경 결정 고정: 명세 원문, 추가 지시, `EXTENSION_STATUS.md`를 대조합니다.
2. 위험 기반 설계: 원본 손실, 개인정보 잔존, 업데이트 실패, 사용 권한 상실을 우선합니다.
3. 단위·통합 테스트: 메모리에서 만든 문서와 임시 폴더로 정상/경계/실패/취소 사례를 실행합니다.
4. 시스템 테스트: 실제 OCR·Office·LibreOffice·탐색기·설치·업데이트를 확인합니다. 모의 서버 결과를 실서버 결과로 표시하지 않습니다.
5. UI 검사: 실제 동봉 폰트, 100/125/150/175/200% DPI, 키보드와 마우스, 단일/듀얼 모니터, 밝은/어두운 테마.
6. 성능: 문서 종류·크기·환경·샘플 수를 기록하고 엔진 시간과 사용자 체감 시간을 구분합니다.
7. 결함: 재현 입력·기대/실제·수정·회귀 테스트를 기록합니다.
8. 종료 판정: 모든 명시 요구의 구현과 증적을 검토하고 미구현·미검증·목표 미달을 남긴 상태로 정식 완료 처리하지 않습니다.

## 제품 품질별 확인 사항

| 검토 영역 | 어잉PDF 검증 사항 |
|---|---|
| 기능 적합성 | 명세 각 도구·단축키·파일 형식·출력 결과와 원본 보존 |
| 성능 효율성 | 시작/진단/변환/그리기 지연, 메모리 상한, 4K, 상주 프로세스 없음 |
| 호환성 | Windows 10/11, Office/한글/LibreOffice 유무, DPI, 다중 모니터 |
| 상호작용 능력 | 한국어 포함 3개 언어, 포커스, 잘림, 오류 설명, 취소 및 확인 |
| 신뢰성 | 손상 입력, 디스크 오류, 실행 중 종료, 취소, 재실행, 업데이트 롤백 |
| 보안 | DPAPI, 비밀값 미노출, 매크로 방지, 업데이트 검증, 실제 Redaction |
| 유지보수성 | SDK 의존성 고정, 기능 분리, 테스트 추적, 문서·빌드 재현 |
| 유연성 | 포터블/설치형, 시스템 언어, 다양한 입력, 문서 크기와 장치 변화 |
| 안전성 | 삭제 확인, 원본 미수정, 출력 충돌 거부, 오류 시 기존 정상 버전 보존 |

## 실행과 증적

```powershell
.venv_d/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv_d/Scripts/python.exe -m pytest tests -q -o cache_dir=temp/pytest-cache --junitxml=temp/test-results/pytest.xml
.venv_d/Scripts/python.exe tests/ui_regressions.py
.venv_d/Scripts/python.exe tests/ui_smoke.py
.venv_d/Scripts/python.exe tests/viewer_smoke.py
.venv_d/Scripts/python.exe scripts/benchmark_sniffer.py
```

JUnit은 `temp/test-results/pytest.xml`, 진단 벤치마크는 `temp/benchmarks/sniffer.json`에 기록합니다.
정식 배포 직전 증적을 배포 보고서로 보존하고 임시 파일을 정리합니다.
실제 라이선스 키, 개인 문서, OCR 원문을 증적 저장소에 포함하지 않습니다.

## 현재 발견·수정된 결함

| 문제 | 수정 | 회귀 증적 |
|---|---|---|
| 재실행 시 온라인 인증 강제 | DPAPI 활성화 상태로 오프라인 허용 | test_licensing |
| 새 UI 시험에서 폰트 누락 | 시험에도 동봉 Pretendard 등록 | ui_regressions |
| 뷰어와 새 변환 작업의 MuPDF 동시 실행 | 변환을 별도 프로세스로 분리 | test_processes |
| 취소 시 OCR 자식 프로세스·임시 파일 잔존 가능 | Windows Job 소유권과 전용 TEMP/TMP 하위 작업 | test_processes: 실제 자손 프로세스 강제 종료와 OCR 작업 후 임시 폴더 제거 검사 |
| 30ms를 엔진 수치만으로 판단할 위험 | 별도 프로세스 시작 포함 벤치마크 | benchmark_sniffer: 현재 전체 시간 목표 미달 |

성능 최적화, 전체 명세 기능, 배포·업데이트·DPI 전체 검증이 끝나지 않았으므로 현재 정식 종료 게이트는 미통과입니다.
