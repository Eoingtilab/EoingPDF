# 어잉PDF 2

탐색기 우클릭으로 문서를 PDF로 바꾸고, 하나로 합치고, 핵심문장을 빠르게 꺼내는 Windows 포터블 유틸입니다.
메인 앱을 먼저 열 필요가 없습니다. 파일은 외부로 전송하지 않고 원본도 수정하지 않습니다.

## 시작

설치형은 `EoingPDF-2.1.2-Setup-x64.exe`를 실행합니다. 현재 사용자 폴더에 설치되며 시작 메뉴와 우클릭 메뉴, PDF 문서 아이콘을 등록합니다.
설치 마지막 화면에서 기본 PDF 앱 설정을 열 수 있습니다. 제거는 Windows 설정의 설치된 앱에서 **어잉PDF**를 선택합니다.
아래는 포터블 사용 방법입니다.

1. `release/EoingPDF-2.0-portable.zip`을 원하는 위치에 풉니다.
2. 폴더 안의 `install-context-menu.cmd`를 한 번 실행합니다. 관리자 권한은 필요하지 않습니다.
   Windows 기본 앱 설정이 열리면 `.pdf`에 **어잉PDF**를 선택합니다. 이후 PDF를 더블클릭하면 뷰어가 열립니다.
3. 탐색기에서 파일을 선택하고 우클릭합니다. Windows 11에서는 **더 많은 옵션 표시**를 누릅니다.
4. **어잉PDF · PDF로 변환 / 하나로 합치기 / 핵심문장 요약**을 선택합니다.

작은 진행창에서 자동 작업합니다. 결과는 원본 폴더에 새 이름으로 저장됩니다.
서로 다른 폴더의 파일을 합치면 첫 파일의 폴더에 저장합니다. 병합 순서는 탐색기가 전달한 선택 순서이며,
정확한 순서를 지정하려면 `EoingPDF.exe`에서 목록을 정렬하세요.
포터블 폴더를 이동했다면 우클릭 메뉴를 다시 등록하세요. 제거하려면 `uninstall-context-menu.cmd`를 실행합니다.

## 지원 기능

- PDF · 이미지 · Office · 한글 · 텍스트를 혼합하여 PDF 병합
- 문서별 PDF 변환, 페이지 출처가 붙는 오프라인 핵심문장 요약
- 페이지 추출/삭제/순서 변경, 회전, 무손실 최적화
- PDF → PNG ZIP, 텍스트 추출, 페이지 번호
- 파일 드롭, 순서 이동, 페이지 미리보기, 중단, 결과 폴더 열기
- 독립 PDF 뷰어: 페이지 이동, 확대/너비 맞춤, PDF 파일 열기
- 왼쪽 작은 페이지 미리보기 클릭으로 이동. 각 미리보기의 **X → 삭제 확인**으로 페이지 제거
- 삭제는 임시 편집 상태로 유지. **저장 / Ctrl+S**를 눌러 새 PDF 저장. 원본 보존
- **페이지 삭제**에서 `3, 7-9`처럼 여러 페이지를 함께 지정할 수도 있음
- **슬라이드쇼 / F5**: 현재 페이지부터 전체화면. Space/→/↓/왼쪽 클릭은 다음, ←/↑/오른쪽 클릭은 이전, Home/End는 처음/끝, Esc 종료
- 전체화면 오른쪽 위 **전체화면 종료** 또는 **F5**로도 뷰어로 돌아옵니다. 뷰어의 **닫기** 버튼으로 창을 닫습니다.

앱 왼쪽 **PDF 열어보기**로 바로 읽을 수 있습니다. PDF를 `EoingPDF.exe`에 끌어 놓거나 연결 프로그램으로 열어도 뷰어가 실행됩니다.
**우클릭·기본 앱 설정 → 기본 PDF 앱 설정**에서 기본 뷰어 선택 화면을 다시 열 수 있습니다.
Windows의 기본 앱 선택은 Windows 설정에서 확인하며, 앱이 기존 연결을 강제로 덮어쓰지 않습니다.

| 형식 | 필요한 프로그램 |
|---|---|
| PDF, JPG, JPEG, PNG, WEBP, BMP, TIFF | 없음 |
| TXT, CSV, MD | 없음. UTF-8/UTF-16/CP949 지원 |
| DOC, DOCX, RTF | Microsoft Word |
| XLS, XLSX, XLSM | Microsoft Excel |
| PPT, PPTX, PPTM | Microsoft PowerPoint |
| HWP, HWPX | 한컴 한글. 보안 확인창이 나타날 수 있음 |

Windows에서 열 수 있는 모든 파일을 지원하는 것은 아닙니다. 형식별 실제 검증 현황은 `docs/VALIDATION.md`를 확인하세요.
요약은 원문 문장 빈도에 기반한 발췌이며 생성형 AI 요약이 아닙니다. 스캔 이미지는 Windows 내장 OCR을 자동 사용합니다.
Windows 한국어 OCR 언어팩이 필요하며, 인식 결과는 원문과 비교해 주세요. 본문 수정, 암호 해제, 생성형 AI 연결은 현재 포함하지 않습니다. 무손실 최적화는 용량 감소를 보장하지 않습니다.
서명·양식·책갈피 등 특수 문서는 결과를 확인한 뒤 사용하세요.

## 개발 실행 / 테스트 / 빌드

Python 3.11 이상과 Windows 10/11 x64에서 실행합니다. 우클릭 연결 프로그램에는 Windows의 .NET Framework 4.x를 사용합니다.
네이티브 모듈 빌드에는 Visual Studio 또는 Build Tools의 C++ 데스크톱 개발 도구와 Windows SDK가 필요합니다.

```powershell
python -m venv .venv_d
.\.venv_d\Scripts\python.exe -m pip install -r requirements.txt
.\.venv_d\Scripts\python.exe main.py
.\.venv_d\Scripts\python.exe main.py --quick merge "문서.pdf" "이미지.png"
.\.venv_d\Scripts\python.exe -m unittest discover -s tests -v
.\build_release.ps1
```

빠른 명령: `--quick convert`, `--quick merge`, `--quick summary`. `--folder`로 저장 위치를 지정할 수 있습니다.
`--manifest`는 UTF-8 파일 목록을 받습니다. 탐색기 연결 프로그램은 COM IDropTarget으로 전체 선택을 한 번에 전달합니다.
API 키 설정이나 상주 서비스는 없습니다. 글꼴은 Pretendard를 포함합니다.

## 구조

`src/eoingpdf/`: 처리 엔진과 화면 · `native/`: 우클릭 연결 · `tests/`: 검증 · `assets/`: 폰트
`docs/`: 설계/검증/라이선스 · `release/`: 배포본 · `logs/`: 개발 로그 · `outputs/`: 결과 · `backups/`: 이전 작업

## 변경 이력

2.0: 우클릭 중심으로 재작성. 새 UI, Pretendard, 독립 변환 프로세스, 혼합 병합, 로컬 발췌 요약.
기존 코드는 `backups/legacy-20260911/`에 보관합니다.
