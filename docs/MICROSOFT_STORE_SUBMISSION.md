# 어잉PDF Microsoft Store 최초 제출 준비서

기준일: 2026-10-29
기준 소스: Eoingtilab/EoingPDF의 공개 main 2.4.3
Store 통합 작업: feature/microsoft-store-2.4.3 (ROOM-PC 별도 작업트리)
상태: 제출 준비 중. Partner Center 제품·실제 Package Identity가 확인되기 전에는 패키지·제출 완료로 표시하지 않는다.

## 배포 원칙

- Microsoft Store 판은 전체 MSIX, Windows Desktop x64로 제공한다. 앱과 업데이트는 Microsoft Store가 관리한다.
- 기존 EXE 설치본, 포터블 EXE, GitHub/NallaApps 배포 파일은 수정·삭제·대체하지 않는다.
- build/modern-shell/EoingPDF.Shell.unsigned.msix는 우클릭 메뉴용 실험 패키지다. Store에 제출하지 않는다.
- 앱 이름을 중복 예약하지 않는다. 기존 제품 확인 후, 없는 경우 MSIX/PWA 제품 유형으로 한 번 예약한다.
- 정확한 Partner Center Package/Identity/Name, Package/Identity/Publisher, PublisherDisplayName을 취득한 후에만 최종 MSIX를 빌드한다. 임시 CN이나 가상 제품 ID를 제출하지 않는다.
- 이 작업트리의 앱 버전은 2.4.3이며 MSIX 버전 표기는 2.4.3.0이다. 최소 Windows 10 빌드 19041, Windows 11 지원.

## 상품 정보

- 제품 표시명 후보: 어잉PDF (영문 표기 EoingPDF). 예약 제품의 실제 이름을 우선한다.
- 게시자: Partner Center의 승인된 조직 게시자 이름과 일치하도록 설정
- 가격: 무료. **최초 무료 라이선스 발급·활성화에는 날라앱스 계정과 인터넷 연결이 필요하다.** 이 사실을 스토어 목록에서 숨기지 않는다.
- 소개·지원 URL: https://app.nal.la/downloads/%EC%96%B4%EC%9E%89pdf/
- 고객지원: https://app.nal.la/support/
- 개인정보처리방침 후보: https://github.com/Eoingtilab/EoingPDF/blob/main/PRIVACY.md (main에 공개되고 외부에서 접속 가능해야 사용)
- 오픈소스: https://github.com/Eoingtilab/EoingPDF (AGPL-3.0)

## 한국어 스토어 문안

### 짧은 설명

어잉PDF는 Windows에서 PDF 변환·병합·페이지 편집·OCR·양식·직인·발표 판서까지 처리하는 무료 데스크톱 PDF 도구입니다.

### 자세한 설명

어잉PDF(EoingPDF)는 파일을 PDF로 바꾸거나 여러 문서를 하나로 합치고, PDF를 열어 페이지를 편집하며, 직인과 양식을 추가할 수 있는 Windows용 데스크톱 프로그램입니다. 일반적인 문서 작업은 사용자 PC 안에서 처리하며, 문서 원본을 서비스 서버에 올릴 필요가 없습니다.

PDF 열기, 페이지 추출·삭제·회전·재배열, 병합·분할, 워터마크·페이지 번호, 문서 비교, 암호 설정·해제, 텍스트 추출, Windows OCR을 이용한 스캔 문서 처리, 발표·판서, 인쇄용 4쪽 모아찍기와 소책자 작업을 지원합니다. 파일 탐색기 우클릭 메뉴에서 PDF 변환·병합·핵심문장 요약을 실행할 수도 있습니다.

지원 형식에는 PDF, 이미지, 텍스트, Microsoft Office, 한글 HWP/HWPX 등이 포함됩니다. Office나 한글 파일의 일부 변환 기능에는 해당 데스크톱 프로그램 설치가 필요할 수 있고, OCR에는 Windows 언어팩이 필요할 수 있습니다.

한국어·영어·일본어 인터페이스와 밝은/어두운 테마를 지원합니다. 무료로 사용할 수 있지만 처음 사용할 때 날라앱스에서 무료 라이선스 키를 발급·활성화해야 하며, 계정 로그인 및 최초 인터넷 접속이 필요합니다.

### 주요 기능

1. PDF 열기, 페이지 편집·추출·삭제·회전·정렬
2. 이미지·Office·한글 문서 PDF 변환 및 PDF 병합·분할
3. 양식 만들기·작성, 직인·서명, 워터마크·페이지 번호
4. Windows OCR, 텍스트 추출·검색, PDF 문서 비교
5. PDF 발표·판서, 4쪽 모아찍기와 소책자 인쇄
6. 파일 탐색기 우클릭 변환·병합·핵심문장 요약

### 이번 버전에서 달라진 점

2.4.3: PDF 도구 화면의 아이콘·버튼 스타일을 통일하고 테마, 화면 배율, 작은 창에서도 버튼 배치를 개선했습니다. 검증된 PDF 편집·변경 내역 기능은 유지됩니다.

## English Store copy

**Short description:** EoingPDF is a free Windows desktop PDF utility for document conversion and merging, page editing, OCR, forms, stamps, and presentations.

**Description:** EoingPDF supports local PDF viewing, conversion, merging, splitting, page editing, forms, stamps, watermarks, comparison, and presentation annotations. Routine document operations are performed locally on your Windows PC. Korean, English, and Japanese interfaces are provided. Some Office/HWP conversions require the corresponding desktop software; Windows OCR language packs may be needed. A free NallaApps account, free license key, and initial online activation are required.

## 최종 제출 전 점검표

1. Partner Center에서 기존 어잉PDF 제품이 있는지 확인하고, 중복 예약을 방지한다.
2. 정확한 제품 ID, 패키지 이름, Publisher DN 및 게시자 표시 이름을 취득한다.
3. 최신 Store 통합 소스의 자동 테스트·정적 검사·Windows 실행 검증을 통과한다.
4. Store-aware 폴더 빌드를 생성하고 build_store_msix.ps1에 **실제 등록된 Identity**를 넣어 MSIX를 만든다. Manifest/버전/EXE/DLL 포함 여부와 SHA-256을 검증한다.
5. 실제 2.4.3 화면 스크린샷을 확보한다(최소 1장, 권장 4장: 메인 작업공간, 파일 병합, 페이지 편집·직인, 양식/발표). 과거 UI나 합성 화면을 제출하지 않는다.
6. 개인정보처리방침 공개 URL의 정상 접속을 검증한다. 무료 라이선스 발급 과정과 필수 외부 프로그램을 목록에 명확히 기재한다.
7. 가격·지역·카테고리·연령 등급·Store 목록·runFullTrust 제한 기능 사용 사유를 확인한다.
8. 최초 라이선스 등록이 필요한 경우, Microsoft 심사팀이 실제 사용할 수 있는 **전용 테스트 계정·무료 라이선스**를 발급·검증하고 심사 메모에 제공한다. 비밀번호·키·토큰은 소스/Git/로그에 기록하지 않는다.
9. Microsoft Store **첫 제출은 Partner Center 웹 UI**로 진행하고, GitHub Actions를 사용하지 않는다.
10. Submit for certification 이후 제품 ID·제출 시각·심사 상태를 확인한다. 실제 게시 완료 전에는 앱 출시를 완료로 보고하지 않는다.

공식 안내:
- https://learn.microsoft.com/en-us/windows/apps/publish/get-started
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/create-app-submission
- https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-certification-process
## 준비 완료된 실제 화면 캡처

- 저장 위치(ROOM-PC): outputs/store-submission/screenshots/ — Git 관리에서 제외되는 로컬 제출 자료이며 MSIX에 포함되지 않는다.
- 2026-10-14 최신 2.4.3 UI 회귀검사의 **실제 Qt 창 캡처**를 원본 그대로 복사했고 SHA-256 일치 확인했다.
- 01-PDF-Workspace-Korean.png: 한국어 PDF 작업 공간(1440×1230)
- 02-PDF-Workspace-Dark.png: 다크 테마 작업 공간(1440×1230)
- 03-Presentation-Ink.png: 발표 및 판서 화면(1440×1230)
- 04-PDF-Stamp.png: PDF 직인 배치 화면(1020×720)
- 05-English-Workspace.png: 영문 PDF 작업 공간(1440×1230)
- 06-Japanese-Workspace.png: 일본어 PDF 작업 공간(1440×1230)
- 모두 **프로그램이 렌더링한 실제 UI**이나, 문서 내용은 UI 테스트용 합성 PDF다. Microsoft 제출 전에 스크린샷 1장 이상을 직접 검토한다.

## 2026-10-29 로컬 빌드 검증 결과

- Store-aware 2.4.3 통합 소스의 관련 단위 테스트 **49 PASS**, Pyflakes PASS.
- PyInstaller x64 폴더 패키지 빌드 PASS. 빌드 위치: release/EoingPDF/.
- 빌드된 2.4.3 폴더에서 4개 frozen smoke(기본/PDF·양식/영어·일본어/업데이트 도우미) PASS.
- 실행 파일 SHA-256: AD60D6A0FAACDC7D20EE7ECB3D5764E3264EF5600E594791E4C91DF072600D9B.
- 임시 **가짜 식별자 검증용 MSIX**(실제 앱 제출 불가)를 한 번 생성하여 makeappx·ZIP CRC·manifest version 2.4.3.0·필수 EXE/Explorer DLL 포함 검사를 PASS, 검증 직후 해당 MSIX 삭제. 현재 제출 가능한 최종 MSIX는 **없음**.
- 실제 Partner Center 계정 로그인·앱 제품 ID·Package Identity가 미확인이다. 이에 따라 제품 신규 생성·중복 예약·실제 Package Identity 기반 최종 MSIX·심사 제출은 **미실행**.

## 2026-10-30 인증 실패 수정 후보

위 2026-10-29 기록 이후 실제 제품 ID 9PDKHM1SCBZ9와 기존 제출 패키지 2.4.3.0을 확인했습니다. 라이선스 HTTPS 오류를 수정한 별도 **2.4.4.0** 후보, 실제 frozen 통신·키 활성화·완료 안내, 전체 730개 검사와 MSIX 무결성 결과는 [인증 실패 수정 검증서](STORE_HTTPS_FIX_20261030.md)를 참조하세요. 운영 배포·GitHub Actions·Microsoft 재제출은 하지 않았습니다. 외부 구매 선언 저장 상태의 직접 재확인과 실제 Store 서명 설치 검증은 남아 있습니다.
