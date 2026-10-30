# 어잉PDF 2.4.4

배포일: 2026-10-30 · Windows 10/11 x64

## 라이선스 서버 HTTPS 연결 수정

일부 패키징 환경에서 라이선스 서버에 연결하지 못하던 문제를 수정했습니다. Python 확장과 다른 프로그램의 OpenSSL DLL이 섞이지 않도록 빌드 입력을 고정하고, SSL 초기화에 필요한 정책 파일을 함께 포함합니다. 인증서와 호스트 검증, 리다이렉트 차단은 유지합니다. 키가 잘못된 경우와 서버·연결·TLS·응답 오류를 구분합니다.

최초 라이선스 활성화가 끝나면 성공 안내를 한 번 표시하고, 확인을 누르면 창을 닫습니다. 이미 활성화된 앱의 시작 방식과 일반 라이선스 설정창 동작은 유지합니다. 기존 DPAPI 라이선스 파일을 삭제하거나 인증을 우회하지 않습니다.

## 배포 형태

- 설치형: `EoingPDF-2.4.4-Setup-x64.exe`
- 단일 실행 포터블: `EoingPDF-2.4.4-portable.exe`
- 폴더 포터블: `EoingPDF-2.4.4-portable.zip`
- Microsoft Store 제출 후보: `EoingPDF-2.4.4-Store-x64.msix` — 버전 2.4.4.0, 미서명. Microsoft 심사 제출은 별도이며 Store에 출시됐다는 뜻이 아닙니다.

Store 설치판은 Microsoft Store가 업데이트를 관리합니다. 일반 설치형·포터블의 업데이트는 공식 GitHub 매니페스트와 각 파일의 SHA-256을 검증합니다. 기존 2.4.3 배포본은 보존합니다.

## 검증 및 범위

수정 후보의 실제 frozen EXE에서 공식 서버의 invalid JSON 응답, 연결 거부, 자체 서명 인증서 거부를 확인했습니다. 사용자가 격리된 시험 프로필에 직접 입력한 키의 실제 활성화·완료 안내와 DPAPI 저장을 확인했고, 동일 시험 기기의 상태 확인·비활성화·재활성화 후 시험 등록을 해제했습니다. PDF·OCR·검색·양식·다국어·복원 회귀도 검사합니다.

형태별 실행파일·업데이트 다운로드·소스 ZIP과 최종 SHA-256은 [공개 배포 검증 기록](https://github.com/Eoingtilab/nalapps-releases/blob/main/products/eoingpdf/2.4.4/validation.json)에 기록합니다. [Store 수정 후보의 상세 시험](STORE_HTTPS_FIX_20261030.md)은 공개 배포 전의 로컬 검증 기록입니다. 실제 Microsoft 심사 PC와 Store 서명 설치 환경은 별도 검증 범위입니다.
