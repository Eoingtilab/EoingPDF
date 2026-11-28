# 어잉PDF 2.5.2 변경 사항

## 핵심 개선 요약

1. **오른쪽 도구 목록(`PDF 도구 · 프로세서`) 떨림 및 설명 잘림 수정 (`inline_tools.py`, `tool_browser.py`)**
   - 도구 목록에 가로 스크롤바 비활성화(`ScrollBarAlwaysOff`), 픽셀 단위 스크롤(`ScrollPerPixel`), 리사이즈 자동 배치(`QListView.Adjust`), 항목 간격 정리(`setSpacing(0)`)를 적용해 창 크기·패널 폭 변경 시 가로 스크롤바가 깜빡이며 목록이 떨리는 현상을 해결했습니다.
   - `ToolDelegate.sizeHint()`가 항목 여백·테두리·아이콘 폭을 정확히 반영해 텍스트 줄바꿈을 계산하도록 보완하여 일부 도구 설명(`PNG 워터마크` 등) 하단이 잘리던 문제를 개선했습니다.
   - `test_right_tools_dock_no_horizontal_scrollbar_or_oscillation` 회귀 테스트를 추가해 125% / 150% DPI 환경에서도 정상 동작함을 검증했습니다.
