# 어잉PDF 2.5.1 변경 사항

## 핵심 개선 요약

1. **업데이트 안내 배너 및 업데이트 완료 알림 (`updates.py`, `update_helper.py`, `portable_update.py`)**
   - 백그라운드에서 새 버전을 내려받을 때 상단 알림 배너로 진행 상황을 안내합니다.
   - 다운로드가 완료되어도 열려 있는 창을 예고 없이 종료하지 않고, 상단 배너에서 **\[지금 업데이트\]** · **\[닫을 때 적용\]** · **\[알림 닫기\]** 중 선택할 수 있습니다.
   - 업데이트 후 재실행 시 상단에 `어잉PDF 2.5.1 버전으로 업데이트가 완료되었습니다!` 배너와 **\[단축키 안내\]** 바로가기를 표시합니다.

2. **Stirling PDF v2 디자인 일체감 강화 (`inline_tools.py`, `library_panel.py`, `viewer_workspace.py`, `viewer.py`)**
   - 오른쪽 **PDF 도구 · 프로세서** 패널 상단에 검색(`Ctrl+K`), 분류 필터, `RECOMMENDED`(6종 추천 도구 칩), `ToolDelegate` 설명형 도구 카드를 바로 배치했습니다.
   - 왼쪽 **보관함**에 파일명 검색 필터와 페이지 수 표시를 추가하고, 활동 레일에 테마 전환·단축키 안내(`F1`)·설정 버튼을 배치했습니다.
   - 상단 헤더의 **슬라이드쇼 · F5**와 **직인·서명 넣기** 강조를 유지하면서 뷰어 툴바 카드와 `Your PDFs. Your control.` 환영 홈 화면을 정돈했습니다.

3. **전체 단축키 및 53+ 도구 전수 점검 (`workbench_dialogs.py`, `inline_tools.py`)**
   - `F1` 단축키 안내 창과 `Ctrl++`/`-`/`0`/`1`/`2`(배율), `Ctrl+R`/`Ctrl+Shift+R`(회전), `Ctrl+B`/`Ctrl+J`(좌우 패널 전환), `Ctrl+M`, `Ctrl+D`, `Ctrl+F`, `Ctrl+I`, `Ctrl+P`, `Ctrl+W`, `Home`/`End`를 추가했습니다.
   - `decrypt`(해제할 암호 입력), `ocr_redact`(추가 가릴 단어), `overlay_pdf`(배경 PDF 암호), `bates`(기존 번호 가리기), `qr_stamp`(현재 페이지 반영) 옵션을 인라인 도구 실행기에 반영했습니다.
