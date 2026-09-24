# 공통 SDK 적용 현황

기준: `Eoingtilab/nalapps-windows-sdk`, 커밋 `181fa2a1b8d6f96435563a9d175a9d9de227ccde`.
확인일: 2026-09-13. 어잉PDF 작업 버전은 2.2.0이며 이 문서는 최종 출시 완료 보고서가 아닙니다.

## 확인된 구조와 결정

공통 SDK는 .NET/WPF이며 기존 어잉PDF는 Python/PySide6입니다. WPF 컨트롤을 Qt 위젯처럼 직접 사용할 수 없습니다.
현재 단계에서는 원본 `NalaApps.DesignSystem.xaml`을 변경 없이 고정 버전 의존 리소스로 포함하고,
Qt 어댑터가 실제 `NalaApps.Color.*` 토큰을 읽습니다. 제품별 색상 표를 새 기준으로 만들지 않습니다.
SDK 원본 리소스의 SHA-256과 커밋은 `assets/nalapps-sdk/provenance.json`에 기록했습니다.
앱 실행 중 SDK 다운로드나 상주 동기화 프로세스는 없습니다.

SDK README와 실제 XAML은 v3.0인 반면 일부 설계 문서는 v1.2/이전 색상입니다.
이번 어댑터는 실제 XAML의 v3.0 색상과 README를 기준으로 합니다.
이는 WPF App Shell/License Center/Update Center 전체 연동 완료를 의미하지 않습니다.

## 적용 범위

| 영역 | 현재 처리 | 남은 작업 |
|---|---|---|
| PDF 엔진 | 기존 기능 유지 | MASTER SPEC 확장 |
| 디자인 토큰 | 원본 XAML 읽기 + 무결성 검사 | SDK 업데이트 도구 및 호환성 검사 |
| Qt 메인/뷰어/팝업 | 공통 토큰 적용 | 공통 화면 구조·접근성·전체 DPI 검증 |
| Pretendard | 기존 동봉 폰트 유지 | 굵기별 리소스 일관성 검증 |
| 라이선스 | 기존 DPAPI/기기 ID 유지, 최초 인증 후 오프라인 허용 | SDK 서비스 어댑터와 상태 모델 통합 |
| 업데이트 | SHA-256 필수·다운로드/실행 직전 검증 | SDK 백업·롤백 계약 및 실서버 검증 |
| 배포 | assets 자동 포함, 소스 ZIP 목록 보강 | 새 설치파일 빌드 및 설치·업데이트 검증 |

실제 사용자 라이선스 키와 설정을 저장소에 복사하지 않습니다.
SDK 리소스는 앱 빌드 시 함께 배포되므로 GitHub 접속이 없어도 UI를 표시합니다.
공통 SDK 자체의 원격 코드나 배포 상태는 이 작업에서 수정하지 않았습니다.

## 검증

2026-09-14: Qt 설정 진입점을 일반/라이선스/업데이트 탭으로 통합했습니다.
기존 서비스 호출을 재사용하며 업데이트 중복 확인 방지·설치 대기 상태·창 종료 시 타이머 정리를 검사했습니다.
이는 SDK의 WPF 설정 컨트롤이나 로그 센터·체크섬/롤백 계약 구현 완료를 의미하지 않습니다.

`tests/ui_regressions.py`에서 최초/다음/리사이즈 너비 맞춤, 페이지 화살표, 한국어 기본 버튼,
작은 창의 파일 선택 버튼, 새 보조 도구의 옵션 전환을 확인합니다.
UI 테스트도 실제 동봉 Pretendard를 로드하도록 수정했습니다.
SDK 전체 마이그레이션 및 ISO 인증을 완료했다고 표시하지 않습니다.

## 2026-09-17 테마 후속 구현

- `sdk_theme.install_theme`: 시스템/밝게/어둡게 설정을 QSettings에 보관하고 Qt 색상 변경 신호로 적용한다. 상주 서비스나 테마 폴링은 없다.
- upstream XAML의 색상 역할과 색조를 유지하며 어두운 명도를 계산한다. 공식 SDK 다크 토큰이라고 주장하지 않는다.
- 슬라이드쇼 청중 화면은 고정 어두운 스타일을 사용한다. 공통 `Border`/`Text` 치환으로 발생하던 힌트·종료 버튼 대비 충돌과 글꼴 규칙 유실을 수정했다.
- Quick 진행창은 Windows 언어 선택과 ko/en/ja 리소스에 연결했다. 전체 엔진 오류 번역 완료를 뜻하지 않는다.
- `windows_effects.py`: 지원되는 Windows 11 기본 프레임의 제목 표시줄 테마와 Mica/Acrylic을 DWM API로 요청한다. Qt 콘텐츠 영역과 PDF/판서 픽셀은 불투명하게 유지한다.
- 고대비/투명 효과 끄기/원격 세션/배터리 절약/합성 불가/미지원 OS는 단색 폴백. 설정 변경·활성화·테마 이벤트로 갱신하며 OS 설정은 변경하지 않는다.
- 네이티브 API 호출 실패 시 단색으로 복귀한다. Windows 10은 기본 프레임을 유지한다.

공식 API 근거: [DWM_SYSTEMBACKDROP_TYPE](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type),
[DWMWINDOWATTRIBUTE](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute),
[Mica 폴백 조건](https://learn.microsoft.com/en-us/windows/apps/design/style/mica).

실제 Windows 11 build 26200에서 제목 표시줄 dark 플래그와 backdrop 값을 읽어 확인했다. 현재 PC는 투명 효과가 꺼져 있어 실제 결과는 단색이다.
고대비·원격 세션 조건은 정책값 주입으로 검사했고 실제 OS 모드를 변경하지 않았다. Mica/Acrylic 시각 효과 전체와 고대비 콘텐츠 접근성은 추가 검증 대상이다.
`tests/theme_windows_smoke.py`는 실제 windows 플랫폼을 요구하며 client 이미지와 DWM 상태를 `temp/theme-windows/`에 기록한다. 비대화형 테스트 데스크톱의 화면 캡처는 검정이어서 client 캡처로 대체했으며 네이티브 프레임 시각 검증으로 표현하지 않는다.

추가로 `temp/theme_dpi_check.py`에서 실제 Windows Qt 백엔드에 프로세스 한정 `QT_SCALE_FACTOR` 1/1.25/1.5/1.75/2를 적용했다. 3언어×2테마×뷰어/설정×5배율 = 60조합에서 페이지 제어의 창 내부 배치, 너비 맞춤, 테마 선택 폭, PDF 원본 보존을 확인했다. 결과와 client 이미지는 `temp/theme-dpi/`에 있다. 영어 설정과 일본어 뷰어 이미지를 확인했으며 설정의 셸 상태 문구 등 미번역 문자열은 남아 있다. OS 배율 설정 변경이나 실제 모니터 간 이동 시험은 아니다.
