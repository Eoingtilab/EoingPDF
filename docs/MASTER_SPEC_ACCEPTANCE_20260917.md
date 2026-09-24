# MASTER SPEC 수락 검증표 — 2026-09-17

범위: `MASTER_SPEC_V2.md` 원문과 `CONTINUATION_HANDOFF_20260917.md`의 확정 변경.
현재 전체 목표는 진행 중이다. 최신 설치 빌드의 자동 검사 528개 통과(75.99초)와 후속 `/S` 스크립트 4개 검사를 전체 요구 수락이나 정식 출시 승인으로 간주하지 않는다.
아래 테스트 파일은 `tests/`, 구현 파일은 별도 표기가 없으면 `src/eoingpdf/` 기준이다.
`구현·검사`는 명시한 로컬 검사 범위의 증거이며, 우측 항목까지 완료되었다는 뜻이 아니다.

## 아키텍처·디자인

| 명세 | 구현·검사 | 남은 수락 조건 |
|---|---|---|
| 0.1 SDK·Fluent·소재·테마 | sdk_theme, windows_effects; test_sdk_palette, test_theme_switching, test_windows_effects, theme_windows_smoke. Qt 프로세스 배율 100/125/150/175/200%에서 3언어·2테마·뷰어/설정 60조합 검사 | 원본 SDK는 밝은 색상만 제공. Qt 어두운 어댑터/기본 프레임 효과만 구현. 콘텐츠 소재·전체 고대비·물리 모니터 간 DPI 이동과 접근성 필요 |
| 0.2 ko/en/ja·OS 언어·셸 | localization, assets/locales, generate_shell_strings; test_extended_localization 포함. 35개 고급 도구와 엔진 오류/작업 상태 리소스화, 자식 프로세스 언어 전달. 실제 Windows 54화면/문서 필드 보존 검사 | 후속 번역 소스 재빌드 검증 진행. 실제 각 OS 언어의 설치·탐색기 노출 수락 필요 |
| 0.3 비상주 | 요청 시 child 실행·process_scope·창 종료 타이머 해제; test_processes, test_sniffer_lifecycle, presenter UI 검사 | 최종 설치본의 전체 작업 종료·장시간 메모리 측정 |
| 0.4 단일 EXE·셸 스위치 | 폴더형 ZIP와 단일 EXE, distribution 및 shell_cli/settings; test_distribution, portable_smoke, portable_shell_smoke | 단일 EXE 자동 교체/복원과 현대식 셸 등록 미완료 |

## 선제 진단

| 명세 | 구현·검사 | 남은 수락 조건 |
|---|---|---|
| 진단 30ms·선택/우클릭 | sniffer, sniffer_ui; test_sniffer*, benchmark_sniffer | 이전 합성 cold 전체 경로 약 270ms로 목표 미달. QuickLook 선택 트리거 미구현 |
| D-01 증빙 감지·안심 제출 | sniffer, submission, imaging; test_submission, test_imaging, test_sniffer_extended | 비표준 크기+키워드 감지. 모서리 기울기 조건·실문서 탐지율·OCR 누락 평가 |
| D-02 스캔/인코딩·검색 가능 | sniffer, ocr; test_searchable, test_tounicode_repair | 전체 폰트 유실 사례·1초 전체 처리 목표 미검증 |
| D-03 정보 유출 | 메타데이터/주석 진단, sanitize; test_sanitize, test_sniffer | 비가시 코멘트/수정 이력 전 범위 탐지·제거 수락 필요. 주석은 별도 확인 안내 |
| D-04 발표/인쇄 제안 | 가로 비율·10쪽 감지, four_up/booklet; test_sniffer, test_imposition | 실제 프린터·비표준 슬라이드 추가 검증 |
| D-05 배경 인쇄 | print 트리거, print_light; test_print_light, test_sniffer_extended | 90% 토너 절감 미측정. 전체 이미지형 슬라이드는 보존 정책상 반전하지 않음 |
| D-06 계약/직인 평탄화 | 키워드 기반 감지·300DPI flatten; test_advanced, test_sniffer | 실제 서명 이미지 감지와 오탐/미탐 평가 |
| D-07 숫자 표 | 선/숫자 비율 감지, clipboard_tools; test_clipboard_tools, clipboard_ui_smoke | 복잡한 표·실제 Excel/한글 붙여넣기 호환 |
| D-08 연속 캡처 | capture_ui; test_capture_ui | 앱/뷰어가 보일 때 클립보드 이미지 구독. 앱 미실행 시 Win+Shift+S 전역 감지는 하지 않음 |
| D-09 추천 파일명 | sniffer heading·금지문자/예약명 처리; test_diagnostic_rename | 실제 문서 제목 품질과 작업별 접두/접미 명명 평가 |
| D-10 비교 슬라이더 | visual_diff/diff_ui/advanced_ui; test_visual_diff, diff_ui_smoke | 처리 후 비교 연결. 처리 전 미리보기·전체 도구 자동 연결은 수락 미완료 |

## 발표 및 판서

| 명세 | 구현·검사 | 남은 수락 조건 |
|---|---|---|
| 2.1 F5/Shift+F5·듀얼 4K | viewer/presenter; test_presenter_ink, presenter_ui_smoke | 실제 듀얼 4K 발표 시험 |
| 현재/다음·타이머·페이스 | presenter; presenter_ui_smoke | 장시간 경과·실제 진행 시간 품질 |
| PDF 주석 대본 | presenter의 주석/스티커 읽기; presenter_ui_smoke | 모든 주석 종류·실제 문서 대본 검증 |
| B/W/G/S/Ctrl+L/Space | presentation_canvas/slide_grid; test_presentation_boards, presenter_ui_smoke | 스캔/다단 커튼·실제 장치 조작 |
| 2.2 Direct2D·관통·120fps | native InkOverlay/GpuInkSurface, native_ink; test_native_ink, native_ink_ui_smoke | GPU 제출 벤치마크와 실제 지속 4K/120fps를 구분. 후자 미검증 |
| 도형 0.1초 스냅 | shape_snap; test_shape_snap | 다양한 필체/펜 장치와 전체 지연 측정 |
| 자석 형광펜 | ink_controller/presentation_canvas; test_ink_tools | OCR 없는 스캔 줄 인식 미지원 |
| 라이브 타이핑 | ink_text; test_ink_text, native_ink_ui_smoke | IME/배율/문서 조합 확대. 저장 글자는 윤곽선 주석 |
| 3초 고스트 | ink_stroke; test_ink_tools | 장시간 실제 발표 시험 |
| B/W 칠판 | viewer/presentation_ink; test_presentation_boards | 실제 발표 저장/취소 수락 |
| 0.5초 레이저 | presentation_canvas/presenter; test_presenter_ink | 실제 프로젝트 화면 시인성 |
| Bake/Discard·역회전 저장 | presentation_ink; test_presenter_ink, test_rotated_overlays | 실제 다중 DPI 장치 좌표/외부 뷰어 확인 |

## 보안

| 명세 | 구현·검사 | 남은 수락 조건 |
|---|---|---|
| S-01 민감정보 영구 삭제 | advanced/submission; test_advanced, test_submission | 주민번호/전화/이메일/Luhn/SSN 실제 코퍼스 오탐·누락 평가 |
| S-02 추적점·숨김 문자 | sanitize; test_sanitize | 작은 노란 그래픽/제로폭 등 합성 검사. 임의 프린터 MIC·마이크로 투명 레이어 전체 제거 보장 없음 |
| S-03 심층 메타데이터 | sanitize/advanced; test_sanitize | 실제 증분 저장·숨은 첨부·경로 전 범위 수락 |
| S-04 300DPI flatten | advanced; test_advanced | 실제 계약서 출력 품질. 래스터 사본도 위변조 불가능을 보장하지 않음 |
| S-05 AES-256·권한 | advanced/advanced_ui; test_advanced, encrypted_viewer_smoke | 외부 뷰어별 권한 처리·장기 사용 |
| S-06 45도/PNG 워터마크 | watermark; test_watermark | 실제 인쇄·외부 뷰어 호환 |

## 문서 지능

| 명세 | 구현·검사 | 남은 수락 조건 |
|---|---|---|
| I-01 Auto AcroForm | forms/form_review_ui/form_ui; test_forms, test_form_review, test_form_choices, form_ui_smoke | 실제 종이 서식 감지율·외부 뷰어 한글 호환 |
| I-02 로컬 ONNX 검색·100MB | semantic_search/search_worker; test_semantic_search, test_search_* | 현재 모델은 retrieval 전용 아님. 한국어 fixture top1 7/10은 이전 측정. 전체 앱 100MB 기준 미달/미입증, 실제 검색 품질 개선 |
| I-03 SVG/DXF·1초 | svg_export/dxf_export; test_svg_export, test_dxf_export | DXF는 path 추출 범위. 글꼴·채움·클리핑 전체 무손실 아님. CAD 호환과 1초 목표 |
| I-04 Stitch/Slice | roll_layout; test_roll_layout, test_sniffer_stitch | 실제 내부 여백·다단 문서·큰 이미지 경계 품질 |
| I-05 글꼴 윤곽선 | text_outlines; test_text_outlines | CMYK/별색/인쇄 프로파일과 외부 인쇄소 호환 |
| I-06 구조화 Markdown | markdown_export; test_markdown_export | 다단·병합 셀·복잡한 제목 구조 및 성능 |
| I-07 CMap 수선 | ocr/advanced; test_tounicode_repair | 기존 매핑 직접 복구와 달리 OCR 레이어 재생성 경로. 실제 깨진 폰트 종류·정확도 |

## 실무 도구

| 명세 | 구현·검사 | 남은 수락 조건 |
|---|---|---|
| O-01 목표 용량 | compression; test_compression | 실제 화질/최소 용량 한계·대량 문서 |
| O-02 Bates/TOC | bates; test_bates | 기존 번호 탐지/가리기 실제 품질·복잡한 목차 |
| O-03 도장·암호 금고 | stamping/seal_vault; test_stamping, test_seal_vault, stamp_ui_smoke | 다른 계정/PC 이동 안내·실제 휴대폰 도장 품질 |
| O-04 비주얼 Diff | visual_diff/diff_ui; test_visual_diff, diff_ui_smoke | 실제 계약서 오탐/렌더링 차이 평가 |
| O-05 손상 복구 | recovery; test_recovery | 광범위 손상 코퍼스, 복구 불가 사례 안내 |
| O-06 일괄 이미지 교체 | image_replace/image_choice_ui; test_image_replace | 수백 개 실제 파일 스트레스·공유 이미지/색공간 |
| O-07 사진 보존 다크 | advanced/viewer; test_smart_dark | 사진/도표 복합 실제 문서 품질 |
| O-08 Staging Dock | staging_dock, --dock; test_staging_dock의 실제 PDF 병합·순서·중복·원본 보존·취소·닫기·경계 검사, Windows 3언어×2테마 UI | 실제 탐색기 드롭·다중 물리 모니터 이동·대량 문서 수락 |

## 기본 유틸과 배포

| 명세 | 구현·검사 | 남은 수락 조건 |
|---|---|---|
| E-01 책 스캔 분리 | advanced; test_spread_split | 실제 스캔/용지 호환 |
| E-02 백지 제거 | advanced; test_advanced | 스캔 노이즈·희미한 내용 보존 |
| E-03 여백 자르기 | advanced; test_rotated_trim | 실제 도형/주석/링크 복합 문서 |
| E-04 역순 | advanced; test_advanced | 최종 설치본 수락 |
| E-05 300DPI 복사 | clipboard_tools; test_clipboard_tools, clipboard_ui_smoke | 외부 앱 붙여넣기 |
| E-06 범위·묶음 분할 | splitter/core; test_splitter, test_engine | 최종 설치본 수락 |
| E-07 HTML+TSV 복사 | clipboard_tools/selection_canvas; test_clipboard_tools, clipboard_ui_smoke | 실제 Office/한글 표 서식 100% 보존 주장 불가 |
| 7.1 탐색기 Space·50ms | 독립 PDF 뷰어 기반 | 선택 트리거와 50ms cold 시작 미구현/미달 |
| 7.2 Micro-Edit | viewer·보조 도구·사본 저장 | 프리뷰 내 복사/마스킹/회전 전 흐름·QuickLook 연결 |
| 7.3 winget | packaging/winget 초안 | 최종 URL/해시·서명·제출/승인 |
| 7.3 Silent /S | install-silent.cmd /S → Inno /VERYSILENT 등, 실제 설치/재설치/제거 및 오류 코드 전달 검사 통과 | 현재 사용자 설치 범위. 설치 EXE 직접 호출 시에는 Inno 표준 옵션 사용 |
| 7.3 서명 | unsigned native DLL/sparse msix 생성 | 사용자 서명 인증서 또는 Artifact Signing 설정 필요. 자체 신뢰 인증서를 설치하지 않음 |
| Windows 11 현대식 메뉴 | ExplorerCommand DLL 및 sparse manifest; test_explorer_command, test_modern_shell_package, native_shell_invoke_smoke의 성공 Invoke/다중 선택 소비 | 프로세스 경계 기록용 EXE를 실제 라이선스 GUI와 구분. 서명 등록/제거·탐색기 노출 미검증 |

## 후속 확정 요청

| 요구 | 현재 증거 | 남은 조건 |
|---|---|---|
| EDD 상품 26818·최초 활성화 후 오프라인 | licensing.ITEM_ID=26818, test_licensing; 이전 실제 valid/offline 확인 | 실제 비활성화→재활성화→재부팅 |
| EDD 자동 업데이트·복원 | SHA-256·독립 도우미·스냅샷, test_updates/test_update_helper/test_update_snapshot | 서버 버전/체크섬 설정, 실제 교차 버전 설치·중단·강제 종료 복구 |
| HWP 사용자 모아찍기 무관 1쪽씩 | hwp_pdf PrintToPDFEx, test_hwp_pdf | 실제 RegisterModule=False 해결 후 hwp_one_page_smoke·특수 용지 |
| Office/한컴 미설치 폴백 | libreoffice·원자적 convert, test_libreoffice/test_conversion_publication | 실제 Office/HWP/HWPX/LibreOffice 형식별 호환 |
| 최종 설치·정리·문서 | build_release, installer_smoke, QUALITY_PLAN | 최신 설치본 시험, 정리 후보 안전 확인, 코드/배포 반영 |

EDD 상품 관리 화면: https://app.nal.la/wp-admin/post.php?post=26818&action=edit (사용자 제공).
이는 서버 소스 위치나 서명 설정 정보가 아니다.

다음 작업은 공개 여부나 외부 계정 설정에 의존하지 않는 구현·검증부터 진행한다.
서명/서버/하드웨어 미확인 항목은 별도 잔여 항목으로 유지하고 전체 목표를 완료 처리하지 않는다.
