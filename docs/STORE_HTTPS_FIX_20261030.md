# Microsoft Store 라이선스 HTTPS 수정 검증 — 2026-10-30

이 문서는 공개 배포 전 Store 수정 후보의 검증 기록입니다. 이후 승인된 GitHub 배포와 설치형·포터블 검증은 [2.4.4 릴리스 안내](RELEASE_NOTES_2.4.4.md) 및 공개 배포 검증 기록을 참조하세요. Microsoft 심사 제출은 여전히 별도입니다.

제품 9PDKHM1SCBZ9, 작업 브랜치 `feature/microsoft-store-2.4.3`의 별도 수정 후보입니다. 기존 제출본 2.4.3.0을 보존하고 **2.4.4.0**을 생성했습니다. 운영 배포, GitHub Actions, 패키지 업로드 및 Microsoft 재제출은 실행하지 않았습니다.

## 1. 정확한 원인

기존 PyInstaller Analysis가 `_ssl.pyd`는 Python 배포본에서, `libcrypto-3-x64.dll`과 `libssl-3-x64.dll`은 PATH의 PHP 8.4 폴더에서 수집했습니다. Python은 OpenSSL 3.5.8을 사용하지만 패키지의 DLL은 PHP용 OpenSSL 3.0.21이었습니다. `_ssl.pyd`가 요구하는 `X509_STORE_get1_objects` 심볼이 해당 libcrypto에 없어 SSL import가 실패합니다. `http.client`가 이 ImportError를 처리한 뒤 HTTPSConnection을 정의하지 않고, urllib의 HTTPSHandler도 등록되지 않아 `URLError: unknown url type: https`가 발생했습니다. 해당 모듈들은 PYZ에 있어 단순 hidden import 누락이 아닙니다.

DLL을 바로잡은 실제 EXE에서 두 번째 의존성 누락도 확인했습니다. 이 빌드 Python의 ssl.py는 인증서 거부 정책인 `codex-rejected-cas.pem`을 SSLContext 생성 시 읽습니다. 누락된 파일 때문에 `create_default_context()`가 FileNotFoundError로 실패했습니다. 원래 906바이트의 정책 파일을 그대로 포함하여 거부 정책을 유지했습니다.

임시 진단 코드의 함수 내부 `import ssl`은 지역변수 범위 때문에 별도의 UnboundLocalError를 일으킬 수 있었습니다. 임시 환경변수 로그와 함께 제거했습니다.

## 2. 이번 수정 파일

- `VERSION`: Store 수정 후보 2.4.4.
- `packaging/EoingPDF.spec`, `packaging/frozen_ssl.py`: Python 동반 OpenSSL DLL 지정 및 최종 TOC 정규화, 참조하는 인증서 거부 정책 파일 포함. 필요한 원본이 없으면 빌드를 중단합니다.
- `src/eoingpdf/licensing.py`: 검증하는 SSLContext와 HTTPSHandler 명시, 리다이렉트 차단 유지, 서버·TLS·연결·응답 오류 구분, 임시 진단 로그 제거. LicenseStore의 DPAPI 및 활성화 상태 처리 방식은 유지합니다.
- `src/eoingpdf/network_check.py`, `main.py`: 실제 EXE의 읽기 전용 연결 검사. 매번 허구 키로 check_license만 호출하며 사용자 저장소를 읽거나 인증 권한을 생성하지 않습니다. 키·기기 ID·예외 원문을 보고서에 기록하지 않습니다.
- `src/eoingpdf/health_check.py`: 오프라인 frozen 건강 검사에 SSL 초기화와 검증 설정 확인 추가.
- `src/eoingpdf/license_ui.py`: 최초 활성화 성공 안내를 한 번 표시한 뒤 확인을 누르면 종료. 기존 활성 사용자 자동 진입 및 일반 설정창 동작은 유지합니다.
- `assets/locales/ko-KR.json`, `en-US.json`, `ja-JP.json`: 새 오류 문구 번역.
- `tests/test_frozen_ssl.py`, `test_license_transport.py`, `test_license_notice.py`, `frozen_license_smoke.py`: 패키징·전송·완료 안내 및 실제 frozen 실패 경로 검사.
- 이 검증 문서. 기존 staged Store 준비 변경은 그대로 보존했습니다.

## 3. HTTPS 처리 전후

| 항목 | 기존 제출본 | 수정 후보 |
|---|---|---|
| OpenSSL DLL | PATH의 PHP DLL과 Python 확장 혼합 | 같은 Python 배포본의 확장·DLL |
| SSL 정책 데이터 | 누락 | 원본 바이트와 SHA-256 일치 |
| HTTPS 처리 | 처리기 등록 실패 | 명시적인 검증 SSLContext·HTTPSHandler |
| 인증서·호스트 검증 | 런타임 초기화 자체 실패 | CERT_REQUIRED·check_hostname=True |
| 오류 | HTTPS 미지원으로 보임 | 서버 오류·연결 실패·TLS 실패·키 거절 구분 |

## 4. 실제 frozen EXE 검증

최종 v4의 동일 EoingPDF.exe에서 다음을 확인했습니다.

- 공식 app.nal.la에 허구 키를 상태 조회하여 정상 JSON invalid 응답 수신 PASS.
- 프로세스에만 적용한 닫힌 루프백 프록시로 연결 거부를 만들어 connection 오류 및 권한 미생성 확인 PASS.
- 별도 루프백 TLS 프록시의 자체 서명 인증서를 실제로 거부하여 tls 오류와 TLSV1_ALERT_UNKNOWN_CA 확인 PASS.
- 모든 경우 인증서·호스트 검증 유지. Windows 인증서 저장소 변경 없음, 시험 TLS 개인키 잔여 없음.
- 번들의 `_ssl.pyd`, SSL·crypto DLL, 정책 PEM이 빌드 Python 원본과 해시 일치.

## 5. 실제 활성화와 저장·해제 검증

사용자가 최종 frozen EXE의 격리된 라이선스 창에 본인 키를 직접 입력하여 활성화했습니다. 완료 안내가 한 번 표시되고 확인 후 창이 닫히는 동작도 사용자가 확인했습니다. 키는 채팅·명령줄·Git·로그에 기록하지 않았습니다.

같은 Windows 사용자 안의 별도 LOCALAPPDATA/APPDATA를 사용했습니다. DPAPI 재로딩 및 파일 내 키 평문 부재 PASS. 동일 시험 기기 ID로 실제 상태 확인 → 비활성화 → 재활성화 → 상태 확인 → 비활성화 PASS. 이 후속 수명주기 검사는 소스 Python의 실제 LicenseStore/request로 실행했으며, 모든 후속 요청을 frozen으로 검사했다고 주장하지 않습니다. 최종 EXE 안내 확인 후에도 해당 시험 등록만 해제해 추가 슬롯을 남기지 않았습니다. 원래 사용자 라이선스 파일은 복호화·수정하지 않았으며 기존 파일 해시가 같습니다.

## 6. 회귀 검사

- 최종 전체 pytest **730 PASS, 실패·오류·skip 0**, 150.55초.
- Pyflakes 및 diff 공백 검사 PASS.
- 최종 frozen 4종 검사 PASS: PDF 렌더링·변환·OCR·ONNX 검색, 자동 양식·공유 필드·한글 입력, 영어·일본어·Unicode 경로, 복사본의 업데이트 복원.
- 최초 실행의 누락된 평가 모델·도구는 별도로 준비했습니다. 위 수치는 보충 합산이 아닌 최종 전체 재실행 결과입니다.

## 7. 새 MSIX

- 파일: `release/EoingPDF-2.4.4-Store-x64.msix`
- 크기: 165,571,871바이트.
- SHA-256: `d9d9023fdf213f64025be596a74a48bff315fce917f40f3371e6beeeebfec12e`
- Identity: EoingtiLabInc.PDF / CN=54ECF930-FC04-4042-BEC5-C05C15E95287 / 2.4.4.0 / x64.
- ZIP CRC·중복/안전 경로·필수 파일·Manifest·388파일/5,772블록의 SHA-256 전수 검사 PASS.
- Store 제출용 미서명 후보입니다. 서명 신뢰 또는 Store 설치 실행을 이 무결성 PASS에 포함하지 않습니다.

## 8. 보존 확인

기존 2.4.3 MSIX SHA-256은 `716082e0e0613792cb50769960b1aab87e8ac7189f5c6f355c33e2ee9ba5020c`로 보존됐습니다. 기존 Store 폴더 EXE, 기존 staged 패치와 사용자 암호화 라이선스도 시작 시점의 근거와 비교했습니다. 기존 임시 진단 빌드도 정식 산출물로 교체하지 않았습니다. 작업 시작 백업·패치·검사 로그는 원본 프로젝트의 `temp/store-httpsfix-20261030-174307/`에 있습니다.

## 9. 재심사 제출 상태

로컬 수정 후보와 기술 검증은 완료했습니다. Microsoft에 업로드·재제출하지 않았습니다. 10.8.2 외부 구매 선언은 변경하지 않았으며, 사용자가 이미 저장했다고 한 상태를 유지했습니다. Aside 세션은 미로그인 상태였고, 로그인된 Whale 속성 창은 Computer Use 읽기 접근 승인 시간 초과로 해당 선언의 저장 상태를 직접 재확인하지 못했습니다. 재제출 전 그 항목을 확인해야 합니다.

## 10. 남은 검증 범위

- Microsoft 심사 PC의 재검증 및 Store 서명 패키지 설치·업데이트 실행은 미실행입니다.
- 별도 앱 데이터로 격리했으며 새 Windows 계정/VM을 생성한 검사는 아닙니다.
- 외부 구매 선언의 저장 상태 직접 재확인이 남아 있습니다.
- 기존 사용자 데이터 삭제, 인증 우회, TLS 검증 비활성화, 운영 서버 설정 변경, 운영 배포 및 GitHub Actions는 실행하지 않았습니다.

공식 규격: [Microsoft Store 패키지 버전 규칙](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/package-version-numbering?pivots=store-installer-msix), [PyInstaller spec의 바이너리 수집](https://pyinstaller.org/en/stable/spec-files.html), [Python SSLContext](https://docs.python.org/3.12/library/ssl.html).
