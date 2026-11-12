# 어잉PDF Microsoft Store 제출 준비서

기준: 2.4.13 / 기존 제품 ID `9PDKHM1SCBZ9`. Store의 현재 제품 상태, Package Identity, Publisher 및 게시자 표시명은 Partner Center에서 직접 대조한 후에만 패키지를 만들고 제출한다. 기존 EXE·포터블·GitHub 릴리스는 변경하지 않는다.

## 배포와 이용 조건

- 개인·기업·공공기관·교육기관을 포함해 무료로 사용한다. 계정, 키 발급, 온라인 활성화는 필요하지 않다.
- 현재 라이선스는 GNU AGPL-3.0이며 외부 구성요소별 조건도 적용된다. 제3자의 적법한 재배포를 금지하지 않는다.
- NallaApps가 현재 공식 다운로드 채널이다. 기존 Microsoft Store 제품은 심사 및 게시가 완료된 뒤 공식 채널로 안내한다. 기술적 릴리스 저장소와 업데이트 매니페스트는 유지한다.
- Store 버전은 Windows 패키지 상태를 감지하여 자체 업데이트 대신 Microsoft Store 업데이트를 사용한다.
- 제품 안내: https://app.nal.la/downloads/%EC%96%B4%EC%9E%89pdf/ / 지원: https://app.nal.la/support/ / 개인정보: https://github.com/Eoingtilab/EoingPDF/blob/main/PRIVACY.md

## 한국어

**짧은 설명:** PDF 변환·병합·편집과 직인, 양식, 발표를 지원하는 무료 Windows 도구입니다.

**설명:** 어잉PDF는 PDF를 열고 페이지를 정리하며 여러 문서를 합치거나 변환할 수 있는 Windows용 프로그램입니다. 직인·서명 이미지 배치, 입력 양식, 발표 판서, OCR과 문서 비교를 지원합니다. 일반 문서 작업은 PC에서 처리합니다. 무료로 사용할 수 있으며 계정이나 라이선스 키, 온라인 활성화가 필요하지 않습니다. Office·한글 변환에는 해당 프로그램이 필요할 수 있고, OCR에는 Windows 언어팩이 필요할 수 있습니다.

## English

**Short description:** A free Windows PDF utility for conversion, merging, editing, stamps, forms, and presentations.

**Description:** EoingPDF helps you view and organize PDF pages, merge or convert documents, place stamp and signature images, fill forms, annotate presentations, use OCR, and compare documents. Routine document processing takes place on your PC. It is free to use without an account, license key, or online activation. Some Office/HWP conversions require the corresponding desktop software; OCR may require Windows language packs.

## 日本語

**短い説明:** 変換、結合、編集、印影、入力フォーム、プレゼンに対応した無料の Windows PDF ツールです。

**説明:** EoingPDF は PDF の閲覧やページ整理、文書の結合・変換、印影・署名画像の配置、フォーム入力、プレゼン中の書き込み、OCR、文書比較に対応します。通常の文書処理は PC 内で行われます。アカウント、ライセンスキー、オンライン認証なしで無料で使用できます。Office・HWP の変換には対応アプリ、OCR には Windows 言語パックが必要な場合があります。

## 제출 전 확인

1. 기존 제품과 Partner Center 식별자를 확인하고 제품을 중복 등록하지 않는다.
2. 2.4.13 빌드로 별도의 `2.4.13.0` x64 MSIX를 생성한다. 기존 공개 파일은 덮어쓰지 않는다.
3. Manifest, 버전, CRC, 블록맵, 포함 파일, Store 업데이트 분기와 무인증 최초 실행을 검증한다. 서명·설치·실제 업데이트는 별도로 검증한다.
4. 현재 앱의 실제 화면, 지원 및 개인정보 URL, 한국어·영어·일본어 목록을 확인한다.
5. 기존 제품에 제출한 후 접수 상태와 인증 결과를 구별한다. 심사 전 공개되었다고 안내하지 않는다.

기존 2.4.3/2.4.4 라이선스 인증과 HTTPS 수정 이력은 [당시 검증 기록](STORE_HTTPS_FIX_20261030.md)에 보존되어 있다. 현재 버전은 라이선스 인증이나 심사용 키가 필요하지 않다.

## Store 게시 후 날라앱스 설치 버튼

제품 `9PDKHM1SCBZ9`가 실제로 인증을 통과하여 게시되고 공개 설치가 정상 동작하는 것을 확인한 후, 날라앱스 상품의 기본 다운로드 동선을 Microsoft Store Web Installer로 전환한다. 게시 전에는 설치 가능한 버튼을 노출하지 않는다.

Microsoft 배지 생성기에서 제품 ID `9PDKHM1SCBZ9`, 한국어, 어두운 배경, 시작 모드 `Direct`로 생성한 정적 배지 코드:

```html
<a href="https://get.microsoft.com/installer/download/9PDKHM1SCBZ9?referrer=appbadge" target="_self" >
	<img src="https://get.microsoft.com/images/ko%20dark.svg" width="200"/>
</a>
```

Microsoft의 웹 설치 프로그램이 Store에서 앱을 가져온다. 실제 지원 여부, 파일 서명, Windows 경고, 신규 설치와 Store 업데이트는 **게시 후 별도 검증**하며, 심사 중에는 성공했다고 표시하지 않는다. 공식 안내: https://learn.microsoft.com/en-us/windows/apps/distribute-through-store/how-to-use-store-web-installer-for-distribution

전환 시 상품 본문의 EXE 직접 링크와 키 발급·가입 안내를 정리하고 Microsoft Store 제품 페이지로 연결되는 대체 경로를 함께 제공한다. EDD 공통 카드와 라이선스 생성 설정은 다른 상품·기존 구매자·구버전 활성화에 영향을 줄 수 있으므로 별도 확인 후 어잉PDF에만 적용한다. 기존 릴리스 자산, 과거 라이선스 데이터와 기존 업데이트 매니페스트는 보존한다.
