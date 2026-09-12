# 설치형 빌드

Windows 10/11 x64 현재 사용자용 설치 파일입니다. 관리자 권한을 요구하지 않습니다.
기본 경로: `%LOCALAPPDATA%\Programs\EoingPDF`.
설치 완료 시 우클릭 메뉴, PDF 연결 프로그램 및 문서 아이콘을 등록합니다.
기본 앱 선택은 설치 완료 화면의 선택 항목으로 Windows 설정을 엽니다.
Windows 설치된 앱에서 제거하며 설치 프로그램에 포함되지 않은 사용자 파일은 지우지 않습니다.

## 제작

[공식 Inno Setup 다운로드](https://jrsoftware.org/isdl.php)에서 6.x 컴파일러를 준비합니다. 이번 빌드는 6.7.3을 사용했습니다.
컴파일러의 사용 조건은 공식 사이트를 따릅니다.

```powershell
.\build_release.ps1
.\build_installer.ps1 -Compiler 'C:\경로\ISCC.exe'
```

산출물: `release/EoingPDF-2.1.2-Setup-x64.exe`.
코드 서명 인증서는 적용되지 않았습니다.

## 검증

`tests/installer_smoke.ps1`은 기존 설치형이 없을 때 프로젝트 임시 폴더에 설치/재설치/제거하고 포터블 연결을 복원합니다.
테스트용 PDF는 `tests/viewer_smoke.py`로 준비합니다. 실제 지원 범위는 `VALIDATION.md`를 참고하세요.
