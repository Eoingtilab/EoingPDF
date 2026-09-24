# 설치형 빌드

최신 후속 빌드/검증은 `CONTINUATION_HANDOFF_20260917.md`의 상단 기록과
`../release/VALIDATION-20260917.md`를 기준으로 한다. 아래 날짜별 해시는 과거 빌드 기록이다.

Windows 10/11 x64 현재 사용자용 설치 파일입니다. 관리자 권한을 요구하지 않습니다.
기본 경로: `%LOCALAPPDATA%\Programs\EoingPDF`.
설치 완료 시 우클릭 메뉴, PDF 연결 프로그램 및 문서 아이콘을 등록합니다.
기본 앱 선택은 설치 완료 화면의 선택 항목으로 Windows 설정을 엽니다.
Windows 설치된 앱에서 제거하며 설치 프로그램에 포함되지 않은 사용자 파일은 지우지 않습니다.

## 제작

[공식 Inno Setup 다운로드](https://jrsoftware.org/isdl.php)에서 6.x 컴파일러를 준비합니다. 이번 빌드는 6.7.3을 사용했습니다.
컴파일러의 사용 조건은 공식 사이트를 따릅니다.

`build_release.ps1`가 테스트·PyInstaller·우클릭 연결 프로그램을 만든 뒤
`build/tools/InnoSetup/ISCC.exe`로 설치파일까지 컴파일합니다.

```powershell
.\build_release.ps1
```

Inno Setup 컴파일러가 다른 위치에 있으면 `build_installer.ps1`을 별도로 사용할 수 있습니다.

산출물: `release/EoingPDF-2.2.0-Setup-x64.exe`.
코드 서명 인증서는 적용되지 않았습니다.

단일 EXE 포터블은 `build_portable.ps1`로 별도 제작한다. 이름 변경·격리 실행·PDF/뷰어·검색/드롭존 검사를 통과한 파일만 release에 복사한다. 셸 등록은 `--register-shell`, 해제는 `--uninstall-menu`이며 임시 추출 폴더 밖에 작은 도우미/아이콘을 보관한다. 한 파일의 자동 교체·복원은 아직 미구현이다. 이 파일에는 설치형과 같은 최초 라이선스 활성화가 필요하다.

## 무인 배포 스크립트

`release/install-silent.cmd`와 설치 EXE를 같은 폴더에 놓고 실행한다. 잘못된 버전을 고르지 않도록 해당 폴더에 설치 EXE가 여러 개 있으면 실행하지 않는다.

```cmd
install-silent.cmd /S /DIR="C:\Target Folder\EoingPDF" /LOG="C:\Logs\eoingpdf-setup.log"
```

현재 사용자 계정으로 설치하며 관리자 권한이나 자동 재부팅을 요구하지 않는다. `/DIR`와 `/LOG`는 생략할 수 있다. 로그의 부모 폴더는 미리 준비한다. `/S`는 배포 스크립트의 별칭이며, 설치 EXE를 직접 실행할 때는 Inno Setup의 `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-`를 사용한다. [공식 명령행 문서](https://jrsoftware.org/ishelp/topic_setupcmdline.htm).

스크립트는 설치기 종료 코드를 그대로 반환한다(셸 등록 실패 20 포함). 설치 파일 누락은 2, 여러 파일 발견은 3, `/S` 누락은 64이다. 사용자 라이선스 인증과 기본 PDF 앱 선택은 무인 설치에서 대신 수행하지 않는다.

2026-09-14 빌드 SHA-256:

- 설치파일: `0A283640F3A83BC824544F6055D808187EA5578A215C2B16165047BD7DD31AE6`
- 포터블 ZIP: `E41734D2BAF904095B80257EC27165FB73698DC161DF58982E549CB4544C9CF3`
- 소스 ZIP: `3202927A77228D9349CC8D8FF2CBB2F3EBB93944B2EE5BBF3F02A5D9A44D28CB`

## 검증

`tests/installer_smoke.ps1`은 기존 설치형이 없을 때 프로젝트 임시 폴더에 설치/재설치/제거합니다. 실행 전 연결이 이 프로젝트의 포터블을 가리킨 경우에만 포터블 연결을 복원합니다. 다른 설치의 연결이 있으면 실행하지 않습니다.
테스트용 PDF는 `tests/viewer_smoke.py`로 준비합니다. 실제 지원 범위는 `VALIDATION.md`를 참고하세요.

## 셸 등록 실패 처리 (2026-09-14 소스 변경)

기존 `--register-shell` 오류 경로는 숨겨진 프로세스에서 `MessageBoxW`를 호출하여 사용자 응답을 기다렸습니다. 이제 셸 명령은 오류 팝업 없이 종료하며 다음 코드를 반환합니다.

| 코드 | 의미 |
| --- | --- |
| 0 | 등록 또는 해제 완료 |
| 1 | 배포 파일 누락 등 일반 오류 |
| 2 | 사용자 계정의 셸 설정 권한 거부 |

`--shell-result <파일>`을 지정하면 JSON 결과를 기록합니다. 생략 시 `%LOCALAPPDATA%\EoingPDF\logs\shell-result.json`을 사용합니다. 로그 기록에 실패해도 원래 종료 코드는 유지합니다. 설치 중 결과는 설치기 로그에도 남습니다.

설치기는 파일 복사 후 셸 등록 프로세스의 결과를 확인합니다. 등록 실패 시 파일은 설치되어 있어도 **설치기 종료 코드 20**을 반환하고 앱 자동 실행과 라이선스 입력창을 건너뜁니다. 무인 설치에서는 오류 확인창을 열지 않습니다. 일반 설치에서는 실패를 한국어로 안내합니다. 이는 전체 설치의 자동 롤백을 뜻하지 않습니다.

구현은 Inno Setup의 [공식 이벤트 함수 문서](https://jrsoftware.org/ishelp/topic_scriptevents.htm)의 `CurStepChanged`와 `GetCustomSetupExitCode`를 사용합니다.

검증:

- 실제 `main.py`를 별도 Python 프로세스로 실행한 셸 명령 검사 25개 통과. 레지스트리 작업만 가짜 함수로 바꾸고 팝업 호출을 감시합니다. 권한 오류, 일반 오류, 표준 오류 출력 없음, 로그 기록 실패를 포함합니다.
- 제품 설치기와 동일한 `shell_registration.iss`를 포함하는 격리된 Inno 설치기를 컴파일·실행한 검사 3개 통과. 등록 성공/일반 실패/권한 실패 시 설치기 종료 코드 0/20/20과 로그를 확인합니다. 테스트 EXE를 사용하므로 실제 레지스트리 등록·제품 설치 호환성의 증거는 아닙니다.
- 설치 테스트 스크립트의 초기 실패 및 정리 실패 주입 검사 2개 통과. 최초 오류 보존과 `LOCALAPPDATA`/`QT_QPA_PLATFORM` 복원을 확인합니다.
- 배포 파이프라인 기본 검사 2개 통과. 합계 32개이며 전체 제품 품질 검증의 총수가 아닙니다.

위 변경은 아직 상단 해시의 설치 파일에 포함되지 않았습니다. 실제 최신 제품 설치·업데이트·제거·롤백 검증과 최종 재빌드는 남아 있습니다.
