# FRC-06 legacy `_log` test matrix

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FRC06-LEGACY-TEST-MATRIX |
| 작성일 | 2026-11-27 |
| 관련 | FRC-06, NIP-12, ACF GUI |
| 대상 | `tests/test_chat_scroll.py`, `tests/test_chat_typography.py` |
| 목적 | WebEngine H1 전환 후 레거시 `_log` 단언의 실패·중단 범위를 고정하고 대체 자검을 가리킨다 |

## 1. 결론

두 파일의 `_log` 단언은 숨겨진 QTextEdit 경로를 본다. 현재 보이는 표면은 H1 WebEngine DOM이다. 전체 휠·페이드·QTextDocument fragment 매트릭스를 그대로 옮기려면 큰 재설계가 필요하다. 이번 단위는 실패 행렬을 고정하고, ChatPanel 공개 land/stream API가 H1에 착지하며 ghost `_log`가 비는지 검증하는 `_check_frc06_panel_land`만 추가한다.

## 2. 실패 행렬

| 파일 · 케이스 | 레거시 단언 | 현재 상태 | 대체 |
|---|---|---|---|
| `test_chat_scroll.test_main_and_companion` | `_log.viewport` 휠, `verticalScrollBar` hold/follow, `document().size`, `_top_fade` 픽셀 | `_log` hidden → 단언 무의미. ChatPanel+WebEngine을 `ensure_qt_webengine_ready` 없이 띄우면 0xC0000409/중단 위험 | hold/follow: `iris.ui.chat._check_transcript_scroll`. land 착지: `_check_frc06_panel_land`. 페이드·휠 거리 동등성은 미이전 |
| `test_chat_typography.test_controls_persist_and_restore` | DB/설정 위젯만 | `_log` 없음. 유지 가능 | 그대로 |
| `test_chat_typography.test_invalid_preferences` | `normalize`만 | `_log` 없음. 유지 가능 | 그대로 |
| `test_chat_typography.test_typing_speed_changes_how_many_characters_appear` | `plain_typing_step` + ChatPanel `_typing_index` | ChatPanel 생성 시 WebEngine. ready 패치 없으면 중단 위험 | 순수 step assert는 안전. Panel 절은 skip 또는 `_check_frc06_panel_land` 스트림 경로 |
| `test_chat_typography.test_new_markdown_heading_size` | `_log.document` fragment pixelSize | ghost `_log` 비어 실패 | H1 CSS: `_check_transcript_h1` + `_check_frc06_panel_land` typography |
| `test_chat_typography.test_live_matrix` | `_log` defaultFont / fragment / grab | 동일 + 다중 크기 grab | 라이브 CSS 주입 미구현(manager.changed → `_log`만). 새 land 크기만 `_check_frc06_panel_land` |
| `test_chat_typography.test_stream_positions_and_links_survive` | `_stream_block_start`, `iris-msg-` HTML, `_log.toPlainText` | 커서/HTML은 `_log` 기준. H1은 `data-msg-id` | `_check_frc06_panel_land` stream + msg-id |

## 3. 구조

```
tests (legacy)
  └─ ChatPanel._log  (hidden QTextEdit)  ← 단언이 여기 고정

product path
  ChatPanel.append_message_instant / begin_stream_message
    └─ _land_turn_on_h1 / PartStreamBuffer
         └─ H1TranscriptHost DOM (.turn[data-msg-id])  ← 보이는 표면

FRC-06 this unit
  _check_frc06_panel_land  → land + stream text + data-msg-id + ghost empty
  _check_transcript_scroll → hold/follow (이미 존재)
  _check_transcript_h1 / _check_transcript_no_blank_flash → 렌더·blank (이미 존재)
```

## 4. 코드 리뷰 (경로 지점)

| 지점 | 이번 증상에서 한 일 | 레거시 테스트를 막지 못한 이유 |
|---|---|---|
| `ChatPanel` H1 mount | `_log.hide()`, H1 expand | 테스트가 `_log` API를 직접 호출 |
| `_scroll_log_to_bottom` | H1 `scroll_to_bottom` | 테스트가 `_log.verticalScrollBar` 값 비교 |
| `typography.update_document` | hidden QTextEdit만 재포맷 | H1 `_page_css`는 다음 setHtml/land 때 TOKENS 재독 |
| `ensure_qt_webengine_ready` | 제품 기동 경로에 있음 | unittest가 패치 없이 ChatPanel 생성 |

하지 않은 일: WebEngine 휠 이벤트 패리티, `_top_fade` 픽셀, live CSS inject without re-land, IDE companion 레이아웃 휠 거리 동등성.

## 5. 개선안

| 빈 자리 | 다음 단위 |
|---|---|
| live typography → H1 CSS inject | `manager.changed`에서 style 재주입 또는 token CSS 변수 갱신 + 자검 |
| wheel hold on H1 | DOM `wheel` / `scroll` 이벤트 hold 자검 (Qt QWheelEvent→Chromium 브리지 필요 시 별도) |
| fade overlay | H1에 해당 UI가 없으면 폐기 문서화 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| 기존 `_check_transcript_*` | `ensure_qt_webengine_ready` + `runJavaScript` 프로브 패턴 | 이미 프로젝트 정본 |
| Playwright DOM assert | 브라우저 E2E 스타일 셀렉터 | Qt WebEngine 내장 프로브로 충분 |
| 찾지 못함 | QTextEdit fragment 테스트를 Chromium computedStyle로 1:1 옮기는 표준 하네스 | — |

## 7. 조치

1. `_log` 의존 케이스는 unittest에서 skip (사고 스위트 중단 방지).
2. `python -m iris.ui.chat._check_frc06_panel_land` 를 FRC-06 검증 진입점으로 쓴다.
3. 커밋·push는 사용자 요청 시에만.
