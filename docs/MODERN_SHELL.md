# Windows 11 현대식 탐색기 명령

현재 구현 단계: 네이티브 IExplorerCommand DLL, 실제 COM ABI 검사, 서명 전 sparse 앱 ID 패키지 생성 완료. 신뢰할 수 있는 서명·등록 및 실제 탐색기 메뉴 노출은 아직 미완료다. 기존 클래식 메뉴 등록은 유지한다.

## 구성

- native/ExplorerCommand.cpp: C++17, Windows SDK 인터페이스. Python/Qt를 탐색기에 로드하지 않는다.
- native/build_explorer.cmd: x64 DLL을 assets/EoingPDF.Explorer.dll로 컴파일한다.
- 배포 시 DLL은 EoingPDF.exe와 같은 폴더에 둔다. DLL 자신의 경로에서 실행 파일을 찾으며 PATH 검색을 하지 않는다.
- 각 명령은 IShellItemArray를 받아 선택 순서를 유지한 UTF-8 .files 목록을 현재 사용자 EoingPDF/queue에 기록하고 --quick 명령으로 앱을 실행한다.
- 1,000개/2MB 상한, 지원 확장자 제한, 폴더 제외, CR/LF 및 상대 경로 거부, 출력 목록 CREATE_NEW 생성, 프로세스 생성 실패 시 해당 목록 삭제를 구현했다.
- GetState의 빠른 호출은 E_PENDING을 반환하고, 느린 호출에서 파일명/셸 속성을 확인한다. PDF 분석이나 Office 구동은 Invoke 이전에 수행하지 않는다.
- 명령 제목은 OS UI 언어의 한국어·영어·일본어를 지원한다. scripts/generate_shell_strings.py가 assets/locales의 공통 JSON을 컴파일용 UTF-16 헤더로 변환한다. 탐색기 실행 중에는 JSON/Python을 로드하지 않는다. 누락되거나 유효하지 않은 번역이 있으면 빌드를 중단한다.

| 명령 | CLSID |
|---|---|
| merge | 71BC7F3A-9D38-4AD1-B76C-9B3E1EA45001 |
| convert | 71BC7F3A-9D38-4AD1-B76C-9B3E1EA45002 |
| summary | 71BC7F3A-9D38-4AD1-B76C-9B3E1EA45003 |

## 확인한 범위

2026-09-17: DLL 빌드 및 tests/test_explorer_command.py 3개 통과. 실제 DllGetClassObject → IClassFactory → IExplorerCommand 호출로 제목·정규 GUID·지원 파일 활성 상태·한국어 경로·폴더/지원하지 않는 파일 제외·동일 폴더 앱 누락 시 실패·참조 해제 뒤 DllCanUnloadNow를 확인했다. HKCU/탐색기 등록을 변경하지 않는 검사다.

후속 `tests/native_shell_invoke_smoke.py`는 실제 클래식 DropTarget.Drop과 네이티브 IExplorerCommand.Invoke의 merge/convert/summary 총 6개 경로를 검사했다. 한국어·일본어·공백이 포함된 세 합성 PDF의 선택 순서, UTF-8 목록 소비, 실제 Python jobs 결과, 병합 페이지 순서, 원본 보존을 확인했다. 프로세스 시작 경계는 명령행 기록용 테스트 EXE를 사용하므로 실제 라이선스 GUI나 탐색기 표시의 증거가 아니다. MSIX 호스트의 논리/실제 큐 경로가 달라 정상 목록을 거부하던 문제도 수정했다. 큐 경계·확장자·심볼릭 링크·파일 수/크기 제한은 유지한다.

단일 EXE 포터블의 클래식 등록은 임시 추출 경로 대신 `%LOCALAPPDATA%/EoingPDF/portable-shell`에 도우미와 아이콘을 보관하고 `--app`으로 실제 EXE 이름을 지정한다. `tests/portable_shell_smoke.py`에서 이름 변경, 프로세스 종료 후 도우미 유지, 재등록·해제 및 기존 프로젝트의 등록 값 복원까지 통과했다. 현대식 sparse 패키지는 폴더 배포 경로이며 서명 등록·제거와 탐색기 노출은 여전히 미검증이다.

## 등록 요구

scripts/package_modern_shell.py는 Windows SDK MakeAppx로 build/modern-shell/EoingPDF.Shell.unsigned.msix를 만든다. 패키지는 세 명령의 COM CLSID와 탐색기 verb, 아이콘을 담고 외부 설치 폴더의 EXE/DLL을 참조한다. 실제 인증서 Subject가 결정되면 --publisher로 동일한 값을 지정해야 한다. 기본 CN=Eoingtilab은 개발용 식별값이며 유효한 서명을 뜻하지 않는다. tests/test_modern_shell_package.py는 패키지 내부 연결, 이미지 크기, 잘못된 입력 거부와 SDK를 통한 실제 생성까지 확인한다. 빌드 과정은 인증서를 신뢰 저장소에 설치하거나 패키지를 사용자 계정에 등록하지 않는다.

Microsoft의 [공식 탐색기 통합 문서](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/integrate-packaged-app-with-file-explorer)는 Windows 11 기본 메뉴에 IExplorerCommand와 앱 ID를 요구한다. windows.comServer와 windows.fileExplorerContextMenus를 같은 CLSID로 연결해야 하며, 기존 비패키지 앱에는 외부 설치 폴더를 참조하는 sparse package를 사용할 수 있다. 단순 HKCU 셸 키만으로 현대식 메뉴가 완성됐다고 판단하지 않는다. 서명/등록 정책을 임의로 낮추거나 탐색기 전체를 강제 재시작하지 않는다.
