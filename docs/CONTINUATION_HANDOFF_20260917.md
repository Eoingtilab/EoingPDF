# 어잉PDF 개발 인계 — 새 대화 시작용

작성일: 2026-09-17 (KST). 이 문서는 **현재 개발 상태 인계**이며 정식 출시 완료 선언이 아니다.

## 후속 진행 기록 (같은 날 새 대화)

### 재설치 후 이어가기 — 2026-09-18 저녁 (진행 중)

- 사용자가 정식 완료까지 계속 진행하도록 요청했다. 기존 작업 파일과 인계 기록을 보존했다. 최초 수정 전 주요 파일 백업: `backups/resume-20260918-213848/before-resume.zip`.
- 단일 EXE 전용 업데이트/백업/복원, EDD 포터블 URL/해시 분리, 내장 버전·배포 종류·실행 검사 추가. 범위·서버 계약은 `docs/PORTABLE_UPDATES.md`. 관련 61개 검사 통과.
- 전체 559개 검사(113.51초), Windows 54개 다국어 화면과 기존 UI/frozen 기능 검사 통과. `temp/release-build-resume-20260918.log`.
- frozen 다국어 검사에서 변경 건수 예상 문구 누락과 PDF 공백 U+00A0를 수정했다. 이후 일본어 목차의 누락 글리프를 실제로 발견하여 `pdf_fonts.py`의 내장 CJK 대체를 목차·워터마크·텍스트 변환에 적용했다. 관련 42개 검사 통과. **이 폰트 변경 이후의 최종 전체 빌드는 아직 진행 중**이다.
- 한글 프로세스가 없는 상태에서 `hwp_one_page_smoke.py` 재시도: RegisterModule=False 재현. COM 시작 전에 등록해도 x86/x64 모두 실패. 제품 DLL을 바꾸지 않은 별도 진단 DLL에서 로드/콜백 이벤트 기록이 없어 등록 이전 또는 DLL 로드 단계 문제로 좁혔지만 원인은 미확정이다. 접근 허용 범위를 늘리거나 사용자 문서를 열지 않았다.
- 현재 사용자 인증서 저장소에 코드 서명 인증서 없음. `scripts/check_edd_connection.py --online` 결과 저장된 라이선스 키 없음/오프라인 사용 불가/온라인 검사 미실행. 예전 기록의 valid 상태와 구분한다. 사용자가 답한 **26818은 상품 ID**이며 서버 소스 위치나 서명 설정이 아니다.
- 운영 서버·서명·HWP·QuickLook·성능·실제 장치 수락 항목을 완료 처리하지 않는다. 최신 결과는 후속 기록으로 갱신한다.

### 다국어 후속 소스 — 2026-09-18 (재빌드 진행)

- 고급 도구·양식·비교·발표·설정의 ko/en/ja 문구, 35개 도구 이름/설명, 엔진 오류 231개와 작업 상태/출력 제목을 리소스로 통합했다. 프로세스 경계에서 선택 언어를 전달한다. 내부 작업 ID·원본 필드명/값·경로는 번역하지 않는다.
- `test_extended_localization.py`에서 실제 변환/검색 자식 프로세스의 영어/일본어 결과·오류, 유니코드 경로, 기존 결과/원본 보존과 문서 필드 유지 검증. 엔진 번역 사용만으로 Qt를 불러오지 않는지도 검사한다.
- 중간 전체 검사 542 passed, 148.51s (`temp/localization-suite-20260918.log`, `temp/test-results/localization-20260918.xml`). 이후 출력 제목 번역과 고급 도구 스크롤 영역을 추가했으므로 최종 빌드 게이트에서 다시 검사한다.
- `localization_ui_smoke.py`: Windows 3언어 × 2테마의 고급 도구 3종/양식/비교/설정 3탭/발표자 54화면 검사·캡처. 긴 안내문 줄바꿈과 620×580 고급 도구 내부 스크롤 적용. `temp/localization-ui/report.json` 및 PNG.
- 테마 픽셀 검사는 고정 150ms 대기 대신 초기 진단·너비 맞춤 렌더가 안정된 뒤 비교한다. PDF 픽셀 동일성·원본 보존 검증은 유지한다.
- 새 테스트의 기본 사용자 Temp 접근 거부 때문에 프로젝트 내 새 전용 임시 폴더를 사용했다. 빌드 게이트도 충돌 없는 전용 폴더를 만든다.
- **아래 00시대 설치본은 번역 변경 이전 바이너리다.** 재빌드 검증이 끝나기 전에는 최신 소스와 같다고 간주하지 않는다. 전체 목표와 HWP/서명/서버/성능 미완료 항목은 유지한다.

### 최신 확정 결과 — 2026-09-18 00시대

- 설치·폴더형 ZIP 빌드 완료. 전체 **528 passed, 75.99초**, 정적 검사 0건, Windows UI 및 frozen PDF/OCR/ONNX/업데이트 복원 검사 통과. 로그 `temp/release-build-dock-20260917.log`.
- 단일 EXE 재빌드 완료. 이름을 변경한 EXE 하나만 격리 폴더에 복사해 PDF 변환, 오프라인 뷰어·드롭존, 포함 ONNX 모델의 색인 생성/검색, 원본 보존을 확인했다. 로그 `temp/portable-build-dock-20260917.log`, 결과 `temp/portable-validation/`. 셸 등록→재등록→해제 및 기존 프로젝트 등록 값 복원도 최신 EXE로 통과했다(`temp/portable-shell-smoke-dock-20260918.log`).
- 최신 설치본 설치→같은 버전 재설치→셸 등록→뷰어→제거→사용자 파일 보존 통과(`temp/installer-smoke-dock-20260917.log`). `/S` 별칭 배포 스크립트 `release/install-silent.cmd`도 실제 설치 파일과 동일 시나리오를 통과했다(`temp/installer-silent-smoke-20260917.log`). 설치 EXE 자체의 `/S` 옵션이 아니라 함께 배포하는 스크립트의 별칭이다.
- `/S` 경로·종료 코드·누락/모호한 설치 파일 거부 검사 4개 추가 통과. 기존 설치 검사 드라이버/파이프라인과 8개 묶음 통과. 528개 빌드 테스트와 별도 기록이며 새 전체 수치를 추정하지 않는다.
- 앱 실행 코드와 리소스는 설치/폴더 ZIP/단일 EXE에 반영되었다. 후속 `/S` 스크립트와 검증 문서는 소스 ZIP에 추가 반영한다. 최신 실제 크기/해시는 `release/VALIDATION-20260917.md`와 `release/SHA256SUMS.txt` 기준.
- HWP는 9월 17일 14:42에 생성된 사용자 한글 프로세스가 실행 중이어서 새 변환 시험을 시작하지 않았다. 문서를 저장하고 종료해 달라는 질문은 대기 중이다. 임의 종료나 보안 승인창 조작은 하지 않는다. 별도의 임시 진단 키로 현재 직접 실행/탐색기 실행을 비교한 결과 양쪽 모두 unpackaged이며 키가 보였다. 현재 실패를 MSIX 레지스트리 가상화 탓으로 확정할 증거는 없다(`temp/package-context-report.json`).
- **다음 실제 작업:** 전체 ko/en/ja UI·오류 문자열 누락을 정리하고, 단일 EXE 자동 교체/복원과 QuickLook/성능 요구를 계속 구현한다. 한글 종료 답변이 오면 실제 한쪽 출력 시험을 진행한다. EDD 상품 26818은 확정되어 있으며 서버 소스 위치·서명 설정은 아직 없다. 전체 목표는 계속 진행 중이다.

### 단일 EXE·셸 Invoke·드롭존 구현 경과 (아래 재빌드 예정 표기는 위 결과로 대체)

- `build_portable.ps1`, shared PyInstaller spec의 onefile 모드, `distribution.py`를 추가했다. 이름을 변경한 EXE 하나만 격리 폴더에 복사해 health/PDF transform/viewer 검사를 통과했다. 검색 모델과 `--dock` smoke를 추가하여 재빌드 예정이다.
- 단일 EXE의 클래식 셸 등록은 추출 폴더가 아닌 사용자 데이터 폴더의 작은 도우미/아이콘을 사용한다. 실제 등록→새 프로세스 재등록→해제 및 기존 프로젝트 등록 값 복원까지 통과했다. 다른 설치본이 소유하면 smoke는 중단한다. 자동 업데이트는 아직 수동 파일 교체 안내이며 폴더형 설치기를 포터블 옆에 실행하지 않는다.
- `tests/native_shell_invoke_smoke.py`: 실제 클래식 Drop과 현대식 Invoke 3작업씩 총 6개 통과. 다중 유니코드 선택의 순서, 큐 소비, 실제 PDF 작업과 원본 보존을 확인했다. 기록용 테스트 EXE를 사용하므로 등록된 탐색기 메뉴나 라이선스 GUI 통합 검사와 구분한다.
- MSIX 호스트에서 큐 파일만 실제 캐시 경로로 resolve되어 정상 manifest가 거부되는 문제를 수정했다. 논리 절대 경로의 정확한 부모와 .files, 링크 거부, 크기/개수 제한을 검사한다. 실패한 테스트가 만든 목록 2개는 내용을 확인한 뒤 해당 파일만 삭제했다.
- `staging_dock.py` 및 메인 메뉴/`--dock`: 자석 정렬·항상 위 작은 창, 여러 폴더 수집, 순서 조절, 기본 첫 파일 폴더/선택 폴더에 원클릭 병합, 1,000개 제한, 중복 제외, 원본/출력 충돌 보존, 취소 후 닫기. 창을 닫으면 목록을 비우고 타이머를 정지한다.
- 드롭존 목록의 강한 부모 역참조로 Qt GC 순서에 따른 접근 위반을 재현했다. Qt parent() 관계를 사용하도록 수정한 뒤 드롭존→메인 창 생성 순서 회귀를 통과했다. 31개 통합 관련 검사 및 3언어×2테마 Windows UI 6조합을 확인했다. 화면은 temp/staging-dock-ui에 있다.
- 이 절의 최신 소스는 **아직 12:26 설치 EXE/ZIP에 들어 있지 않다**. 다음 실행 중인 빌드 로그는 `temp/release-build-dock-20260917.log`. 전체 목표/서명/EDD/HWP/하드웨어 등 잔여 요구는 유지한다.

- 섹션 6의 슬라이드쇼 테마 문제 3곳을 수정했다. 고정 청중 스타일을 한곳에 정의하고 반복 전환 시 글꼴·대비·원본 PDF·렌더링 픽셀 보존을 검사했다.
- Quick 진입점을 OS 언어 선택으로 바꾸고 진행창 문구를 ko/en/ja 리소스에 추가했다.
- Windows 기본 프레임 DWM 테마/Mica/Acrylic 요청 및 단색 폴백을 추가했다. 이 PC는 투명 효과 끄기 상태이므로 실환경에서는 단색 폴백과 제목 표시줄 플래그만 확인했다. Qt 콘텐츠 영역 전체의 반투명 구현 완료가 아니다.
- 전체 검사 첫 실행: 499 passed / 1 failed (71.82초). 업데이트 도우미 상태 파일 읽기에 일시적인 PermissionError가 발생했다. 상태 읽기를 대기 상태로 처리하고 원자적 상태 게시도 제한적으로 재시도하도록 수정했다. 관련 26개 검사 통과(1.92초). 테스트에서만 오류를 무시하지 않고 실제 launch 경로도 수정했다.
- 첫 후속 빌드의 전체 507개 검사(76.54초), Windows UI, frozen 도구/검색/복원 및 소스 ZIP 258개 항목 검사를 통과했다. 이후 배포 구성 점검에서 새 `EoingPDF.Explorer.dll`이 스냅샷 관리 목록에 빠진 것을 발견했다.
- 탐색기 DLL을 백업/해시/복원 대상에 추가하고 과거 백업에 없던 신규 관리 파일도 복원 시 제거하도록 수정했다. 복원 도중 실패하면 신규 파일도 원상 복구하며 사용자 DLL/PDF는 보존한다. frozen 복원 검사도 실제 DLL 해시 왕복을 확인하도록 강화했다. 이 수정 후 다시 빌드한다. 아래 오전 설치본 수치와 혼동하지 않는다.
- 사용자가 EDD 상품 편집 URL의 `post=26818`을 다시 확인했다. 제품 `licensing.ITEM_ID=26818` 유지.
- DLL 복원 보완 후 전체 자동 검사 **510개 통과, 82.38초**. JUnit은 `temp/test-results/release-tests.xml`, 빌드 로그는 `temp/release-build-continuation-final-20260917.log`.
- `temp/theme_dpi_check.py`: Windows Qt의 프로세스 배율 100/125/150/175/200% × 3언어 × 2테마 × 뷰어/설정 = 60조합 검사 통과. 실제 물리 모니터 간 DPI 이동과 구분한다. 이미지/JSON은 `temp/theme-dpi/`.
- 요구 번호별 새 수락 검증표: `docs/MASTER_SPEC_ACCEPTANCE_20260917.md`. 성능/서명/서버/실문서 미완료를 유지한다.
- 12:26 KST 후속 설치 빌드 및 설치→동일 버전 재설치→셸 등록→설치본 뷰어→제거→사용자 파일 보존 검사 통과. 설치 120,467,900 bytes / portable ZIP 162,723,512 bytes. 설치 로그 `temp/installer-smoke-continuation-20260917.log`. **미서명 통합 빌드**이며 전체 목표 완료가 아니다.
- 한컴 공식 Automation 보안 모듈 ZIP의 C++ 구현을 대조했다. `IsAccessiblePath(HWND, LONG, LPCTSTR, LPCTSTR)` 네 인수는 현재 구현과 일치한다. 공식 모듈을 실행/등록하거나 보안 설정을 바꾸지 않았으며 기존 RegisterModule=False 원인은 아직 미해결이다.
- 다음 독립 구현: 단일 EXE 포터블의 지속 가능한 셸 등록/해제, 실제 성공 Invoke/다중 선택 소비. 이후 수락 검증표의 미완료를 순서대로 처리한다.

## 1. 새 대화에서 먼저 알아야 할 사항

- 작업 폴더: `D:\4.Dev\1.Utill\008_EoingPDF`
- 저장소: `https://github.com/Eoingtilab/EoingPDF.git`
- 현재 브랜치: `main`. 변경 파일과 untracked 파일이 매우 많다. 기존 변경을 보존하고 `reset`, `checkout`, `clean`으로 초기화하지 않는다.
- 현재 VERSION: `2.2.0`. Python/PySide6/PyMuPDF 기반 Windows 앱이다.
- Python: `.venv_d\Scripts\python.exe`, 셸: PowerShell.
- 사용자 목표: **MASTER SPEC 및 후속 요청을 모두 구현하고, 테스트·정리·설치파일까지 정식 배포 가능한 상태로 완성.** 전체 목표는 아직 미완료다.
- 사용자는 상태 확인만 반복하는 것을 싫어한다. 짧게 확인한 뒤 실제 수정·테스트를 진행한다. 불필요하게 재승인을 묻지 않는다.
- 현재 폴더가 미모2.5 작업을 포함한 최신본이라고 사용자가 확인했다. 다른 최신 브랜치가 있다는 가정으로 시작하지 않는다.
- 최근 변경은 커밋/푸시하지 않았다. GitHub가 로컬 최신 코드와 같다고 주장하지 않는다.
- 마지막 전체 테스트는 종료했다. 인계 시점에 기다려야 할 빌드/테스트 세션은 없다.

## 2. 확정된 제품 요구와 결정

- 핵심은 앱을 먼저 열지 않고 탐색기 우클릭으로 병합·변환·요약을 빠르게 실행하는 것이다. 상주 데몬/시작 프로그램 없이 필요할 때만 실행한다.
- PDF, 이미지, TXT, Office, HWP/HWPX 등 문서를 지원한다. Office/한컴 미설치 대응에 LibreOffice headless 대체 변환을 사용한다. 형식별 실제 호환성 검증은 별개다.
- PDF 뷰어, 좌측 썸네일, 썸네일별 삭제 X와 확인, 최종 저장, 페이지 끝 휠 스크롤로 다음/이전 페이지 이동.
- 기본 PDF 앱 등록 경로 제공. Windows 기본 연결을 사용자 동의 없이 강제로 덮어쓰지 않는다.
- 슬라이드쇼, 전체화면 종료, Space/방향키/마우스 제어, 발표자 HUD 및 판서 확장 요구.
- 앱 아이콘 원본 `C:\Users\maste\OneDrive\Desktop\util.png`, PDF 파일 아이콘 원본 `...\pdf.png`. 제품 assets에 변환된 PNG/ICO가 이미 있다.
- 폰트 Pretendard. 공통 SDK는 `Eoingtilab/nalapps-windows-sdk`.
- EDD 사이트 `https://app.nal.la`, **상품 ID 26818**. 2681은 사용자 오기였으므로 사용하지 않는다.
- 무료라도 최초 라이선스 활성화 필요. **최초 인증 후 오프라인 사용 허용**. 문서 처리는 로컬, 인증·업데이트만 인터넷 사용.
- 설치 시와 앱 설정에서 활성화/비활성화/재활성화. 실행 시 업데이트 검사 및 안전한 설치/복원.
- HWP는 사용자 인쇄 옵션이 모아찍기여도 **문서 1쪽 → PDF 1쪽**이어야 한다.
- README 상세화, 불필요한 코드·프로젝트 파일 정리, 설치파일 최종 빌드 요구.
- ISO/IEC/IEEE 29119와 ISO/IEC 25010 관점의 시험 계획·품질 증거를 작성한다. 테스트 통과를 ISO 인증이나 명세 전체 충족으로 표현하지 않는다.

전체 세부 요구: `docs/MASTER_SPEC_V2.md`와 대화의 EXECUTION DIRECTIVE. 요약에 없는 요구도 삭제하거나 축소하지 않는다.

## 3. 마지막 검증 결과 — 현재 소스와 설치본을 구분할 것

### 현재 소스

- **487개 테스트 통과, 60.33초**.
- 명령: `.venv_d\Scripts\python.exe -m pytest -q -p no:cacheprovider --junitxml=temp/test-results/theme-integration-20260917.xml`
- JUnit: `temp/test-results/theme-integration-20260917.xml`.
- 마지막 정적 검사: `.venv_d\Scripts\python.exe -m pyflakes src main.py scripts` — 0건.
- 단, 후술할 슬라이드쇼 테마 매핑 문제는 검사 범위 밖에서 발견한 **미수정 코드 검토 항목**이다. 487개 통과가 모든 UI/하드웨어 요구 검증을 뜻하지 않는다.

### 마지막 성공한 설치 빌드 (2026-09-17 오전 5시대)

- `release/EoingPDF-2.2.0-Setup-x64.exe`: 120,401,400 bytes.
- `release/EoingPDF-2.2.0-portable.zip`: 162,611,674 bytes.
- `release/EoingPDF-2.2.0-source.zip`: 당시 240 entries / 30,484,004 bytes.
- 해시와 검증 범위는 `release/SHA256SUMS.txt`, `release/VALIDATION-20260917.md` 참고.
- 이 빌드는 당시 자동 검사 459개, Windows UI smoke, frozen PDF/font/도구/검색/업데이트복원 smoke 및 Inno 빌드를 통과했다.
- 설치 → 같은 버전 재설치 → 셸 등록 → 설치본 뷰어 → 제거 → 사용자 파일 보존 검사 통과. **실제 다른 버전으로의 서버 자동 업데이트 검증은 아니다.**
- 로그: `temp/release-build-20260917-retry.log`, `temp/installer-smoke-20260917.log`.
- 스크린샷: `temp/installer-smoke/installed-viewer.png`.
- 아래 원자적 변환 저장, 현대식 셸, 최신 다크 테마 변경은 **이 설치본 이후의 소스 변경**이다. 아직 다시 패키징하지 않았다.

## 4. 최근 해결한 문제 / 구현한 기능

### 뷰어·일반 UI

- 너비 맞춤 초기/다음 페이지/리사이즈 회귀, 페이지 번호 컨트롤, 한글 기본 버튼, 작은 창 파일 선택 버튼 등을 검사했다.
- 전체화면 닫기 경로와 명시적 종료 버튼, 휠 경계 페이지 이동, 페이지 삭제 및 사본 저장 구현이 있다.
- 기본 아이콘·Pretendard를 포함했다. 전체 UI의 모든 문자열과 DPI 조합 검증은 아직 끝나지 않았다.

### 캡처 수집 D-08

- `capture_ui.py`: 앱/뷰어가 보일 때만 클립보드 이미지 변경을 구독. 앱 실행 전 기록이나 텍스트는 읽지 않는다.
- 이미지 2개부터 수집 칩, 순서 변경·삭제·비우기·PDF 저장. 최대 16개/32MB 저장 이미지 예산.
- 마지막 창 닫힘/삭제 시 구독 해제와 메모리 회수. 새 캡처와 저장 중 캡처 충돌 처리.
- 실제 Windows 캡처 단축키 전역 감시가 아니라 클립보드 이미지 이벤트 방식.

### 안심 제출·인쇄 준비

- `submission.py`: 네이티브 개인정보 삭제 → 300DPI 렌더링 → 기울기/그림자 보정 → Windows OCR 좌표 기반 이미지 개인정보 픽셀 삭제 → 새로운 이미지 PDF.
- OCR 분리 토큰 처리, 취소·실패 시 결과 미게시, 실제 합성 전화번호 제거와 내부 픽셀 파기 검사.
- 모든 실제 신분증에서 완벽 탐지를 보장하지 않는다. 이미지 PDF이므로 검색/양식/서명 특성 손실이 있다.
- `print_light`: 삽입 이미지와 유색 도형을 보존하며 어두운 무채색 배경을 밝게 바꾸는 사본 생성.
- 뷰어 인쇄 준비 메뉴에 밝은 사본·4쪽 모아찍기·소책자 연결, 진단 print 트리거 연결.
- 페이지 전체가 하나의 이미지인 스캔 슬라이드는 이미지 보존 때문에 반전하지 않는다. 90% 토너 절감 측정/보증은 없다.

### 원자적 변환 결과 저장 — 설치본 이후

- `convert.to_pdf`: 대상 볼륨의 전용 임시 폴더로 변환 → 유효 PDF/취소 확인 → 새 파일로 게시.
- Windows rename / 다른 OS hardlink로 경쟁 상황에서도 기존 파일을 덮어쓰지 않는다.
- native helper 부분 출력은 전용 임시 경로에서만 제거한 뒤 LibreOffice fallback을 수행한다.
- `libreoffice.convert`도 임시 복사 후 게시. 디스크 오류·취소·동시 생성 파일 보존 검사.
- `tests/test_conversion_publication.py`. 외부 앱은 일부 테스트에서 대역을 사용했으므로 실제 Office/HWP/LO 형식 호환성 증거와 구분한다.
- native helper timeout은 현재 fallback 전에 예외가 난다. fallback 정책을 개선할 때 기존 사용자 Office 프로세스를 종료하지 말 것.

### 코드 정리·업데이트 검사

- pyflakes 3.4.0 개발 의존성 및 빌드 게이트 추가, 제품 미사용 import 5개 제거.
- 이 정리 후 오래된 업데이트 테스트 2개가 `updates.subprocess.Popen`을 모킹하는 문제가 전체 검사에서 드러났다.
- 실제 실행 경계인 `update_helper.launch`를 검증하도록 수정. 작업 중 설치 방지·변조 파일 실행 차단 검사 유지.
- 이전 백업 폴더들을 실제 삭제했다. 가장 최근 정상 백업 `build/previous-release-20260917-052558`는 보존 중. 프로젝트 전체 정리가 끝난 것은 아니다.

## 5. 이번에 추가한 현대식 Windows 11 셸 — 소스만, 등록 미완료

- `native/ExplorerCommand.cpp`, `native/explorer.def`, `native/build_explorer.cmd`.
- `assets/EoingPDF.Explorer.dll` x64 빌드 성공. Python/Qt를 탐색기에 로드하지 않는 네이티브 IExplorerCommand 3개.
- merge/convert/summary CLSID 끝자리 5001/5002/5003, 공통 prefix `71BC7F3A-9D38-4AD1-B76C-9B3E1EA4`.
- DLL과 같은 폴더의 EoingPDF.exe만 실행. PATH 검색하지 않음.
- 선택 순서 유지 UTF-8 `.files` 큐, 최대 1,000파일/2MB, 지원 확장자 제한, 폴더/상대경로/CRLF 거부, CREATE_NEW, 실행 실패 시 자기 큐 파일 삭제.
- GetState 빠른 호출 E_PENDING, 느린 호출 파일명/셸 속성 확인. PDF/Office 실행은 Invoke 이전에 하지 않음.
- `tests/test_explorer_command.py`: 실제 DLL COM ABI, 제목·GUID·파일 상태·한국어 경로·앱 누락 실패·객체 해제/언로드 검사. **실제 성공 Invoke와 다중 파일 소비, 탐색기 메뉴 노출은 미검증.**
- `packaging/modern-shell/AppxManifest.xml`, `scripts/package_modern_shell.py`, `tests/test_modern_shell_package.py`.
- Windows SDK MakeAppx `/nv`로 sparse 외부 앱 ID 패키지 생성. `build/modern-shell/EoingPDF.Shell.unsigned.msix` (42,741 bytes 확인).
- Identity `Eoingtilab.EoingPDF.Shell`, 기본 Publisher `CN=Eoingtilab`, AppId `EoingPDF`. 실제 서명 인증서 Subject와 일치하도록 생성해야 한다.
- **서명/등록/신뢰 저장소 변경은 하지 않았다.** unsigned 패키지를 설치 가능한 정식 배포본으로 취급하지 않는다.
- `scripts/generate_shell_strings.py`: 공통 ko/en/ja JSON → UTF-16 C++ 헤더. 빌드 시 생성하며 탐색기 실행 중 JSON/Python을 읽지 않는다.
- 네이티브 빌드와 패키지 생성을 `build_release.ps1`에 연결. DLL은 최종 앱 루트 복사, PyInstaller 내부 중복 제외.
- 문서: `docs/MODERN_SHELL.md`.

## 6. 가장 최근 작업: SDK 다크 테마 — 소스만, 후속 UI 수정 필요

### 확인한 SDK 상태

- 2026-09-17 GitHub API로 재확인한 main: `181fa2a1b8d6f96435563a9d175a9d9de227ccde` (기존 pin과 동일).
- SDK는 .NET/WPF. 실제 XAML v3.0에는 밝은 색상만 있고 별도 다크/Mica/Acrylic 리소스가 없다.
- 원본 `assets/nalapps-sdk/NalaApps.DesignSystem.xaml`과 무결성 검사는 유지했다. 원격 SDK 저장소는 수정하지 않았다.

### 구현

- `sdk_theme.py`: `theme_colors`, `apply_style`, `install_theme` 추가.
- 어두운 테마는 SDK 색상 역할/색조를 기준으로 명도를 조정하는 **Qt 어댑터**다. upstream 공식 다크 토큰이라고 표현하지 않는다.
- 테마 선택: 시스템 설정 따름 / 밝게 / 어둡게. `QSettings('Eoingtilab','EoingPDF')`, 키 `appearance/theme`.
- Qt colorSchemeChanged 신호로 시스템 변경 반영. 폴링이나 별도 프로세스 없음.
- WeakKeyDictionary에 원본 스타일을 보관하고 바뀔 때 다시 적용하여 색상 치환 누적 방지.
- 메인/뷰어/검색/라이선스/설정/Quick/발표자 HUD/그리드의 adapt_style 호출을 apply_style로 연결.
- app/license/quick 진입점에 install_theme 연결. 설정 일반 탭에 테마 선택 추가. 새 문구 ko/en/ja JSON 포함.
- `tests/test_theme_switching.py`: 명암 대비, 기존 컨트롤·드롭다운·선택 메뉴의 반복 전환, 시스템 신호와 수동 선택, PDF 원본 및 표시 이미지 동일성 검사.
- 실제 Qt offscreen 렌더링으로 메인/설정 화면 확인. 선택 메뉴와 배지 대비 문제를 보고 수정했다.
- 스크린샷: `temp/theme-main-dark.png`, `temp/theme-settings-dark.png`. 메인은 대비 수정 후 다시 촬영했다.
- 실제 Windows 제목 표시줄 다크 처리, Mica/Acrylic, 고대비/투명도 끄기/원격 세션 폴백은 아직 구현·검증하지 않았다.

### 다음에 즉시 수정해야 할 구체적인 코드 검토 항목

1. `viewer.py` SlideShow 생성자 약 605행:
   - `apply_style(self, 'QDialog, QLabel {background:#111827;color:#dbe5f5;border:0;}')`
   - 새 공통 매핑은 `#dbe5f5`를 Border로 취급한다. 발표용 고정 어두운 배경의 밝은 글자가 경계색으로 바뀌어 대비가 나빠질 수 있다. **미수정, 재현/수정 필요.**
2. 같은 곳에서 곧바로 `self.setStyleSheet(self.styleSheet() + ' QPushButton {font-size:15px;font-weight:400;}')`를 호출한다.
   - 원본 스타일 등록 뒤 직접 덧붙여 테마 재적용 시 추가 글꼴 규칙이 사라진다. 하나의 원본 스타일로 통합하거나 명시적 테마 역할로 개선해야 한다.
3. 약 635행 슬라이드쇼 종료 버튼의 `background:#263246;color:white`도 공통 Text 색상 치환과 충돌한다.
   - 다크 모드에서 밝은 배경+흰 글자가 될 가능성. 고정 청중 화면 스타일을 별도 처리하거나 의미 기반 역할로 수정하고 명암 대비 검사 추가.
4. `quick.py`는 여전히 `install_korean`을 사용한다. OS 자동 언어 동기화 요구를 충족하려면 `install_language`와 Quick 문구 리소스를 점검한다.
5. 최신 테마 변경 내용은 `docs/SDK_MIGRATION.md`, `docs/QUALITY_REPORT_2.2.0.md`, README 등에 아직 반영하지 않았다. 이 인계 문서가 가장 최신 설명이다.

## 7. 실환경 미해결 및 사용자 답변 대기

### 한글 HWP 1쪽씩 변환

- 사용자는 한글 문서를 저장하고 한글을 직접 종료했다고 확인했다.
- 실제 한컴 2022 (12.0.0.535), Hancom PDF 드라이버 환경.
- `hwp_pdf.export_pdf`: PrintToPDFEx / Hancom PDF / PrintMethod=0, Range=0, NumCopy=1, ReverseOrder=0, UserOrder=0, 사용자 범위/헤더 초기화, PageCount 확인.
- SaveAs PDF에 의존하지 않는다. `tests/hwp_one_page_smoke.py`는 실제 4쪽 문서를 모아찍기 2쪽 출력 설정으로 만든 뒤 4쪽 단일 출력 확인용이다.
- 최근 실제 검사 실행은 승인되었으나 **RegisterModule=False로 문서 생성 전에 실패**했다. 현재 원인은 승인 차단이 아니다.
- x86 독립 LoadLibrary는 성공했고 IsAccessiblePath export도 있다. `temp/hwp-loader.exe`, `temp/hwp-loader.cs`.
- 기존 조사에서 Registry32/64, HwpAutomation/HwpCtrl, 짧은 이름/직접 경로 등 여러 조합을 시도했다. 같은 설정을 무작정 반복하지 않는다.
- 한컴 공식 참고: https://forum.developer.hancom.com/t/topic/3209 . 빈 모듈명 True는 등록 해제 요청이지 등록 성공 증거가 아니다.
- 보안 설정을 낮추거나 승인창 자동 클릭, 사용자 한글 전체 프로세스 강제 종료 금지. 앱 소유 인스턴스/임시 경로만 관리한다.
- 실환경 모아찍기 독립성 및 특수 용지 크기 검증은 **미완료**.

### EDD / 업데이트

- 최근 실제 check_license 응답 valid, 상품 26818 확인. 새 프로세스의 오프라인 valid session도 확인했다.
- 실제 비활성화→재활성화→재부팅 전체 시나리오는 미검증.
- get_version 응답은 new_version이 비고 SHA-256도 없었다. 현재 코드에서 이를 최신 버전이라고 오표시하지 않고 서버 설정 오류로 안내한다.
- 사용자에게 app.nal.la EDD 연동 코드의 프로젝트/저장소 위치를 질문했으나 아직 답변 없음.
- 후속 사용자 제공 상품 관리 화면: https://app.nal.la/wp-admin/post.php?post=26818&action=edit . 링크를 남겨 달라는 요청에 따라 기록했다. 이 URL은 EDD 상품 26818 편집 화면이며 연동 코드 저장소 위치나 서버 수정 권한 확인을 대신하지 않는다.
- 사용자에게 코드 서명 인증서 또는 Azure Artifact Signing 설정 유무/공개 지문을 질문했으나 아직 답변 없음. 개인키/암호를 채팅에 요구하지 않는다.
- 테스트 라이선스는 입력 화면이 준비되면 사용자가 직접 입력하겠다고 했다. 사용자 실제 키를 문서/로그/저장소에 복사하지 않는다.

## 8. 전체 목표 대비 남은 큰 작업

- 위 슬라이드쇼 테마 회귀 수정, 다크/라이트 전체 UI 및 실제 Windows 제목 표시줄·Mica/Acrylic·접근성/DPI 검증.
- Windows 11 서명된 sparse identity 패키지 + 실제 등록/제거/메뉴 실행. 성공 Invoke와 다중 선택 소비. Windows 10 기존 메뉴 회귀.
- QuickLook 선택 트리거, 단일 EXE 포터블, 최종 winget manifest/배포.
- HWP RegisterModule 실패 해결 후 실제 모아찍기/특수 용지 검증. Office/LibreOffice 실제 형식별 호환성.
- EDD 최신 버전·체크섬 서버 응답 연결, 실제 교차 버전 자동 업데이트, 비활성화/재활성화, 복구·중단 시나리오.
- 모든 UI의 ko/en/ja 문자열 정리와 OS 언어 동기화. 현재 일부 고급 도구/메시지는 한글 하드코딩이다.
- MicroSniffer D-01~D-10 전체 트리거·정확도 및 30ms 목표. 현재 콜드 전체 경로 약 270ms였으며 달성했다고 할 수 없다.
- 실제 듀얼 4K 발표, 120fps Direct2D 판서, 장시간/다중 DPI 하드웨어 시험.
- 검색 모델 품질/메모리 기준: 현재 bundled multilingual static similarity ONNX 모델은 retrieval 전용이 아니다. 소규모 한국어 fixture top1 7/10, top2 10/10. 전체 앱 100MB 이하 달성 증거 없음.
- 보안/복원/양식/암호/워터마크/분할/책 스캔/백지/자르기/복사/차이/복구 등 기존 확장 엔진은 코드와 검사가 있지만 MASTER SPEC 요구별 최종 수락 검증은 별도로 해야 한다.
- README·CHANGELOG·품질 보고서·요구사항 추적표를 최종 실제 기능 기준으로 정리. `docs/EXTENSION_STATUS.md`와 `docs/QUALITY_REPORT_2.2.0.md`에는 과거 시점 설명이 누적되어 있으므로 날짜를 읽는다.
- 불필요한 프로젝트 생성물 정리, 새 설치/포터블/소스 빌드, 설치·업데이트·제거 검증, GitHub 최신 코드/배포 산출물 반영.

## 9. 권장 다음 작업 순서

1. 현재 작업 트리와 이 문서 마지막 테스트 결과를 짧게 확인한다. 다시 전체 탐색/상태 보고부터 반복하지 않는다.
2. **슬라이드쇼 테마 매핑 3곳부터 수정하고 밝게/어둡게 반복 전환 UI 회귀를 추가한다.** 청중 문서/판서 픽셀은 변경하지 않는다.
3. 테마 문서 갱신, 실제 Windows UI 확인 및 Mica/Acrylic 폴백 구현으로 UI 요구를 이어간다.
4. 코드 서명/EDD 서버 위치 답변이 오면 해당 통합을 진행한다. 답변이 없더라도 독립적인 구현/실환경 검사 작업을 계속한다.
5. 기능 묶음이 안정화되면 `build_release.ps1` 실행. 매 작은 수정마다 큰 설치 빌드를 반복하지 않는다.
6. 마지막에는 MASTER SPEC 모든 번호별로 실제 구현/검증/제약을 대조하고, 미완료를 테스트 개수로 덮지 않는다.

## 10. 명령과 주의점

```powershell
.venv_d\Scripts\python.exe -m pyflakes src main.py scripts
.venv_d\Scripts\python.exe -m pytest tests/test_theme_switching.py tests/test_sdk_palette.py -q -p no:cacheprovider
.venv_d\Scripts\python.exe -m pytest -q -p no:cacheprovider --junitxml=temp/test-results/next-integration.xml
.\native\build_explorer.cmd
.venv_d\Scripts\python.exe scripts/package_modern_shell.py
.\build_release.ps1
```

- 소스 테스트는 conftest가 Qt offscreen을 기본으로 지정한다. 이것을 실제 Windows 데스크톱/하드웨어 검증과 혼동하지 않는다.
- 파일 검색은 `rg ... tests -g 'test_*.py'`처럼 쓴다. Windows에서 `tests/test_*`를 rg 경로로 넘기면 실패한다.
- Windows 재귀 삭제는 절대경로·workspace 내부·재분석 지점·사용 중 여부를 검증하고, 개인/혼합 파일을 무작정 지우지 않는다.
- 서명 인증서를 임의 생성/신뢰 설치하거나 보안 정책을 낮추지 않는다.
- 현재 인계 요청은 새 대화 생성/자동 전송 요청이 아니다. 새 작업을 임의 생성하지 않았다.
