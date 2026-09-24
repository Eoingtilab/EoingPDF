# 단일 EXE 업데이트와 복원

단일 EXE는 현재 실행 파일의 이름과 위치를 유지한 채 새 파일로 교체한다. 폴더형 설치 프로그램을 포터블 업데이트로 실행하지 않는다.

## 서버 응답

EDD 상품 **26818**의 `get_version` 응답에 다음 필드가 필요하다.

| 필드 | 설치형 | 단일 EXE |
|---|---|---|
| `new_version` | 공통 새 버전 | 공통 새 버전 |
| `download_link` 또는 `package` | 설치 EXE의 HTTPS URL | 사용하지 않음 |
| `sha256` | 설치 EXE SHA-256 | 사용하지 않음 |
| `portable_download_link` | 사용하지 않음 | 단일 EXE의 HTTPS URL |
| `portable_sha256` | 사용하지 않음 | 단일 EXE SHA-256 |

허용 다운로드 호스트는 `app.nal.la`이며 리다이렉트는 거부한다. 두 종류 파일의 해시를 섞으면 설치하지 않는다. 새 버전 번호가 없으면 최신 버전이라고 표시하지 않고 설정 오류로 안내한다. 위 포터블 필드는 이 앱의 확장 계약이며 EDD 기본 제공 필드가 아니다. 운영 연동 코드에 해당 필드를 추가해야 한다.

## 교체 순서

1. 백그라운드에서 파일을 내려받고 SHA-256을 검사한다.
2. `%LOCALAPPDATA%/EoingPDF/updates/portable-backups`에 현재 EXE 하나와 경로·버전·해시를 기록한다. 옆에 있는 문서나 다른 앱은 복사하지 않는다.
3. 편집·발표·변환을 마칠 때까지 기다린다. 별도 백업 실행본의 복구 도우미가 준비되고 현재 앱이 종료된 뒤 교체한다.
4. 새 EXE가 단일 EXE인지, 내장 버전이 요청 버전인지, PDF 렌더링과 폰트가 동작하는지 검사한다.
5. 같은 폴더의 임시 파일을 검증한 뒤 원자적 이름 교체를 수행한다. PyInstaller 종료 직후의 짧은 Windows 공유 잠금은 제한적으로 재시도한다.
6. 원래 경로에서 다시 실행 검사를 한다. 검사 실패 시 이전 EXE를 복원한다. 검사 프로세스가 시간 안에 끝나지 않으면 실행 중일 수 있는 파일을 덮어쓰지 않고 백업과 실패 기록을 남긴다.

설정의 **이전 버전으로 복원** 또는 실행파일의 `--rollback-update`로 현재 경로에 연결된 검증된 백업을 선택할 수 있다. 이름이나 위치를 변경하면 이전 경로의 백업을 다른 파일에 자동 적용하지 않는다. 복구 도우미와 재시작 프로세스에는 PyInstaller의 독립 실행 환경을 요청하여 원래 프로세스의 임시 추출 폴더 정리에 영향을 받지 않도록 한다.

백업 손상, 대상 파일 변경, 잘못된 버전, 링크/정션 경로는 거부한다. 업데이트 백업은 현재 사용자 데이터 폴더에 남긴다. 전원 중단 및 운영 서버를 통한 실제 교차 버전 배포는 별도 수락 검증이 필요하다.

## 검증 범위

- `test_portable_update.py`, `test_distribution.py`: 실패 복원, 현재 파일/후보/백업 변조, 잠금 재시도, 다른 파일 보존, 실제 별도 프로세스 종료 대기, 포터블 전용 URL 선택.
- `portable_update_smoke.py`: 격리한 실제 단일 EXE의 파일명 유지·버전 검사·교체·복원. 백업 버전 정보만 합성한 동일 빌드 시험이며 실제 EDD 교차 버전 배포 시험과 구분한다.
- `build_portable.ps1`: 위 frozen 검사를 통과한 파일만 release에 복사한다.

참고: [PyInstaller 독립 프로세스 재시작](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html), [EDD Software Licensing API](https://easydigitaldownloads.com/docs/software-licensing-api/).
