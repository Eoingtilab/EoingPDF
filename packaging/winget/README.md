# winget 제출 파일

`manifest.yaml`은 릴리스 전에 URL과 SHA-256을 채우는 제출용 템플릿입니다. winget-pkg 검사는 기본적으로 버전·기본 로케일·설치자 매니페스트를 각각 별도 파일로 요구하므로, 제출 시 이 YAML 문서를 세 파일로 나누거나 `wingetcreate new`로 생성한 뒤 검증합니다.

```powershell
wingetcreate update Eoingtilab.EoingPDF `
  -u https://github.com/Eoingtilab/EoingPDF/releases/download/v2.2.0/EoingPDF-2.2.0-Setup-x64.exe
```

설치 파일의 SHA-256은 빌드 후 `Get-FileHash`로 산출하고 `REPLACE_WITH_64_HEX_SHA256`을 교체합니다. URL과 해시가 채워지기 전에는 이 파일을 공식 제출하지 않습니다.
