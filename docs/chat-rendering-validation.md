# 채팅 렌더링 수정 및 검증

## 2026-10-06 응답 종료 회귀 수정

- Windows 경로 정규식이 인라인 코드의 닫는 백틱과 뒤 문장까지 소비했다.
  경로 문자 범위에서 백틱을 제외해 Markdown 구분자를 보존한다.
- 화자 제거가 평문 `Iris:`만 처리했다. `**Iris**:`, `**Iris:**`와
  반복 접두사를 공통 표시 단계에서 제거하며 코드 내부 문자열은 보존한다.
- Python-Markdown이 지원하지 않는 CommonMark `\\` + 개행을 코드 밖에서만
  지원하는 줄바꿈 형식으로 변환한다. 임의의 역슬래시를 삭제하지 않는다.
- 최종 텍스트 없이 종료하는 스트림도 누적 버퍼를 확정한다. 워크스페이스의
  최종 렌더링도 스트리밍과 같은 `assistant_visible_text()`를 사용한다.
- 미종료 코드의 마지막 백틱은 스트리밍 중에만 보류하고 최종 렌더링에서는
  코드 데이터로 보존한다.
- 재생 컨트롤은 QTextCursor의 별도 블록에 삽입하고 문자 서식을 초기화한다.
  HTML `<p>`만 삽입하면 Qt가 첫 문단을 기존 본문과 합쳐 버린다.

검증: `tests.test_chat_response_end`와 `tests.test_chat_rendering_pipeline`의
10개 테스트 통과. 새 테스트는 짧은/긴/여러 줄/Windows 인라인 경로/닫힌 코드/
미종료 코드 응답을 청크 크기 1·7·전체, 최종 텍스트 유무, 음성 동기화 유무의
72개 조합으로 실제 Qt 위젯에 넣어 종료했다. 이전 메시지, 최종 문장, 단일 화자,
별도 재생 줄, TTS 본문 분리, 워크스페이스 본문 일치를 확인했다.
한글 글꼴을 적용한 실제 Qt 화면 캡처에서도 마지막 문장과 컨트롤 분리를 확인했다.
이 검증은 재현 입력을 사용하는 UI 테스트이며 실제 모델 요청 검증은 아니다.

추가 실행에서 글꼴 테스트는 설정 저장/잠긴 DB/라이브 자료 부재로 실패했고,
이력 테스트 5개는 테스트 더블의 `_history` 속성 부재로 실패했다.
나머지 이력·대화 테스트 54개는 통과했다.

검증 날짜: 2026-10-02 (Asia/Seoul).

## 실제 원인

가장 큰 원인은 `iris/infrastructure/hermes_client.py`의
`_should_emit_assistant_content()`가 `bool(chunk.strip())`로 청크를 판정한 점이다.
공백·개행만 담긴 SSE content delta가 삭제됐다. 실제 수정 전 모델 테스트에서
응답 원문이 한 줄이었고 `---###`, `####1단계`, 표의 `||`가 붙어 있었다.
CSS나 Markdown 파서만 고쳐서는 이 손상을 해결할 수 없다.

이 판정을 `bool(chunk)`로 바꿔 공백, 개행, 들여쓰기를 수신 단계부터 보존했다.
수정 후 동일 모델에서 실제 받은 응답은 제목 앞뒤 빈 줄, 목록과 표 행,
코드 들여쓰기가 포함된 정상 Markdown이었다.

추가 문제는 문단·제목을 span으로 바꾸는 스타일링, 코드 제거 정책,
청크별 공백 정리, Qt에서 동작하지 않는 단위 없는 line-height,
HTML 삽입 후 초기화되는 문서 여백이었다. 이들도 함께 수정했다.

## 렌더링 호출 흐름

1. `HermesClient.stream_chat()`가 `/v1/chat/completions` SSE를 UTF-8/JSON으로 읽는다.
2. `_should_emit_assistant_content()`가 도구 인자 메시지만 제외하고 공백 content는 보존한다.
3. `HermesChatWorker.run()`이 원문 청크를 합치며 `content_chunk`와 `finished_ok`를 발행한다.
4. `MainWindow._on_content_chunk_for_turn()` → `_on_content_chunk()` →
   `ChatPanel.append_stream_chunk()` → `_append_typing_buffer()`가 누적 원문을 유지한다.
5. 48ms single-shot timer → `_flush_stream_ui()` → `_replace_typing_body()` →
   `_iris_paint_html()`가 현재 생성 중인 답변 영역만 교체한다. 이전 메시지를
   매 청크마다 `setHtml()`로 다시 만들지 않는다.
6. `assistant_visible_text()`가 내부 도구 표식을 정리하고 표시용 코드 펜스를 완성한다.
7. `render_iris_message()` → `render_markdown_document()` → `_markdown_body_to_html()`:
   `normalize_markdown_source()` → `_normalize_prose_symbols()` → 기존 Python-Markdown
   (`nl2br`, `fenced_code`, `tables`, `sane_lists`) → `_sanitize_chat_html()` →
   코드 카드/파일 링크 변환 → `_style_chat_html()` → `wrap_document_html()`.
8. 실제 출력은 `ChatLogTextEdit(QTextEdit)`의 `QTextCursor.insertHtml()`이다.
   응답 본문에 `setPlainText()`나 `QLabel.setText()`를 사용하지 않는다.
9. 완료 시 `_on_chat_finished()` → `end_stream_message()` → `finish_typing()` →
   `_render_markdown_body()` → `_insert_iris_body()`가 최종 전체 답변을 재파싱한다.

워크스페이스 채팅도 `ChatLogTextEdit`를 상속한다. `append_iris_chunk()`는 원문을
누적하고 48ms timer의 `_render_iris_buffer()`에서 같은 렌더러를 사용한다.
`end_iris()`는 timer를 멈추고 최종 전체 답변을 다시 렌더링한다.
메인과 IDE companion은 동일한 `ChatPanel`/`ChatLogTextEdit`를 사용한다.

## HTML entity

정상 Markdown → HTML → Qt 경로는 `&#xC640;`를 한글로 디코딩한다.
반면 plain text fallback이나 `html.escape()`를 거친 `&amp;#xC640;`는
entity 문자열 자체를 표시할 수 있다. 기존의 평문 fallback을 제거하고,
Python-Markdown이 없을 때도 Qt의 GitHub Markdown 파서를 사용한다.

표시용 normalization은 본문의 숫자 entity와 한 번 중복 encode된 숫자 entity를
디코딩한다. 코드블록·인라인 코드는 수정하지 않는다. `<`, `>`, `&`를 만드는
entity는 무작정 decode하지 않아 escaped HTML 예제를 HTML 태그로 바꾸지 않는다.
실제 모델 테스트 1~4에는 숫자 entity가 화면에 남지 않았고,
`&#xC640;`, `&amp;#xC785;` 재현 테스트에서도 한글로 출력됨을 확인했다.
이번 실응답에 entity가 없었으므로 과거 화면의 entity 생성 지점을 하나로
단정하지는 않는다. 이모지/폰트 문제로 처리하지 않았다.

## UI 및 Qt 호환성

- 사용자: 배경 테이블을 제거하고 작은 You 라벨을 본문과 연결한 최소 배경 스타일.
- 답변: 문서형 레이아웃, 최대 약 720px 읽기 폭, 작은 창에서 최소 좌우 여백.
- 본문: 15px, Qt에서 실제 적용되는 165% 줄간격, 14px 문단 아래 여백.
- 제목: h1~h6 유지, 24/21/18/16/15/15px, 600 굵기, 제목 위·아래 여백.
- 목록: 실제 ul/ol/li, 항목 간 간격, 중첩 목록 들여쓰기 보존.
- 표: 실제 Qt 표, 구분된 헤더 배경, 셀 padding과 행 경계.
- 코드: 언어·복사 링크가 있는 Qt table 카드, 문법 강조, 원문 들여쓰기 보존.
- 인용문: 실제 blockquote, 좌우 inset과 문단 간격.
- `<p>`의 block margin/line-height와 실제 문서 폭을 Qt 문서 포맷으로 검증했다.
- Qt에서 표시되지 않는 CSS radius를 사용자 bubble 구현의 근거로 쓰지 않는다.
- 본문 화살표/일부 기본 수식은 일반 문자로 변환한다. 코드의 같은 표기는 그대로 유지한다.

## Hermes 첫 실행 crash

오늘 09:37:36의 `hermes/logs/gateway.log`에 다음 오류가 있다:

```text
Another gateway instance (PID 46956) started during our startup. Exiting to avoid double-running.
```

`gateway-exit-diag.log`에는 PID 46956과 34564의 시작이 1초 안에 겹치고,
PID 34564가 `gateway.exit_nonzero`로 종료한 기록이 있다.
해당 실행의 stderr 파일은 비어 있고 stdout에는 시작 배너만 있었다.
따라서 확인된 원인은 중복 gateway 기동 경쟁이다.

실행 명령은 설치된 Hermes Python에서
`-m hermes_cli.main gateway run --quiet --accept-hooks`였다.
cwd는 `%LOCALAPPDATA%/hermes/hermes-agent`, HERMES_HOME은
`%LOCALAPPDATA%/hermes`, API_SERVER_ENABLED=true, host=127.0.0.1,
port=8642, API_SERVER_KEY 존재, PYTHONPATH 없음이었다. 키 값은 보고하지 않는다.

`start/stop/ensure/restart_hermes_gateway()`에 재진입 가능한 lifecycle lock을 적용했다.
동일 IRIS 프로세스의 health/chat/model 워커가 중복 기동하지 않게 한다.
원래도 /health와 인증된 /v1/models를 검사했지만, 시작 화면이 이 비동기 검사를
기다리지 않고 준비완료를 표시했다. 이제 검사가 성공한 이후에만 준비완료를 표시한다.

사용자 오류는 일반 답변 대신 간결한 오류+자세히 보기로 분리했다.
상세창에서는 진단과 저장된 stdout/stderr를 볼 수 있고 키 패턴은 redact한다.
Hermes가 실패하면 현재 요청을 실패로 처리한다. 다른 모델로 조용히 바꾸는
자동 fallback은 추가하지 않았다. 이후 요청은 gateway 상태를 다시 검사한다.

## 실제 모델 테스트

실제 MainWindow를 `test_mode=True`의 별도 대화 DB로 실행했다. 모델 응답은 mock하지
않았다. 입력창의 전송 경로 `_emit_send()` → `_on_user_text()` → 실제 worker를 이용했다.
기존 사용자 대화를 삭제하지 않았고, 음성 출력과 자동 IDE 파일 생성은 테스트에서 껐다.
Hermes + 현재 설정의 gemma4:e2b를 사용했다.

| 테스트 | 실응답 | 결과 |
| --- | --- | --- |
| 1. TCP 초보 설명 | 1,624자 / 약 103초 | 제목·강조·목록·문단 정상, 원문 제목/강조 기호 및 entity 없음 |
| 2. Python 1~100 합 | 1,921자 / 약 113초 | 두 코드블록과 설명 목록 정상, 코드 들여쓰기·복사 원문 유지 |
| 3. SYN/SYN-ACK/ACK 표 | 1,523자 / 약 116초 | 6열의 실제 표와 설명 정상, Markdown 파이프 행 노출 없음 |
| 4. HTTP 흐름 | 2,095자 / 약 136초 | 제목·번호/중첩 목록·인용문·HTTP/HTML 코드블록 정상 |

각 입력에서 생성 중 화면 3장과 완료 화면을 저장했다. 수신된 실제 응답은 최종 코드로
480px와 1100px에서 메인/워크스페이스에 다시 표시해 검증했다. 16개 조합에서
문서 폭이 viewport를 넘지 않았고 원문 제목·강조·entity·표 구분선이 남지 않았다.
실제 Qt 캡처에서 표, 코드 카드, 인용문과 문단 배치를 확인했다.

증거 파일: `.iris_light_test_tmp/chat-live/`의 `test-*-raw.md`, `test-*.html`,
`test-*-stream-*.png`, `final-*-main-*.png`, `final-*-workspace-*.png`,
`results.json`, `layout-results.json`.

## 수정 파일과 주요 함수

| 파일 | 주요 함수/변경 |
| --- | --- |
| iris/infrastructure/hermes_client.py | _should_emit_assistant_content: 공백 content 보존 |
| iris/core/activity_privacy.py | strip_emoji, prepare_chat_text: 공백·들여쓰기·코드·화살표 보존 |
| iris/ui/chat/markdown_normalization.py | normalize_markdown_source: 보수적 구조 보정, 숫자 entity 디코딩 |
| iris/ui/chat/chat_renderer.py | _markdown_body_to_html, _normalize_prose_symbols, _style_chat_html, render_user_message |
| iris/ui/chat/chat_blocks.py | wrap_document_html: 본문 기본 굵기 재설정 |
| iris/ui/chat/chat_display.py | assistant_visible_text, streaming_segments_html: 코드 유지와 공통 렌더링 |
| iris/ui/chat/chat_panel.py | append_stream_chunk, _iris_paint_html, _apply_reading_measure, append_error_message, clear_transcript |
| iris/ui/chat/message_regions.py | speaker_prefix_html: 작은 라벨과 자연스러운 사용자 메시지 연결 |
| iris/ui/shared/theme_tokens.py | Qt 줄간격과 inline code/표 색상 |
| iris/ui/workspaces/workspace_iris_chat.py | ChatLogTextEdit 상속, 누적 buffer, _render_iris_buffer, end_iris |
| iris/system/hermes_gateway.py | lifecycle 직렬화, GatewayDiagnosis.chat_message/detailed_message |
| iris/ui/workers/hermes_workers.py | HermesChatWorker.run: 오류 진단 상세 보존 |
| iris/ui/window/main_window.py | _on_intro_finished, _on_hermes_health, _on_hermes_health_failed, _on_chat_failed |
| tests/test_chat_rendering_pipeline.py | 손상된 Markdown/entity/청크/코드/lifecycle 재현 테스트 |
| iris/ui/chat/_check_chat_blocks.py | 새 렌더 결과에 맞는 기존 통합 검사 |
| iris/ui/chat/_check_chat_readability.py | 실제 Qt 문단·폭·스트리밍 검사 |
| scripts/check_chat_live_rendering.py | 실제 모델 4문장 실행 및 화면/응답 기록 |
| scripts/check_chat_captured_responses.py | 실응답의 최종 스타일·폭·기호·표 재검증 |

## 회귀 검사 및 남은 범위

렌더링 pipeline, Hermes gateway 진단/인증, 대화 저장 단위 테스트 77개와
chat blocks, chat sessions, composer drop, chat images, typing anchor,
chat render/IDE trigger 검사를 통과했다. PDF/파일/폴더 드롭, 첨부 칩,
링크/위키 앵커, 코드 복사 원문, 대화 복원, 스크롤 고정을 검사했다.

IDE 채팅은 동일 ChatPanel과 480px 폭에서 확인했다. 실제 외부 IDE 창에 대한
도킹·포커스 전환의 종단 테스트는 포함하지 않았다. Windows computer-use 스킬은
읽었지만 이 세션에 필요한 node_repl 실행 도구가 없어 사용하지 않았고,
네이티브 Qt 앱의 입력/전송 코드와 캡처로 검증했다.

완전한 LaTeX 조판 엔진은 추가하지 않았다. 일반 화살표, 곱셈, 기본 분수와
text 표기만 읽기 쉬운 문자로 바꾼다. 이미 공백을 잃은 과거 저장 응답은
원래 개행을 완벽히 복원할 수 없으므로 이후 새 응답의 정상 구조 보존이 핵심이다.
이미 실행 중이던 사용자 IRIS 프로세스는 수정 전 모듈을 갖고 있으므로 재시작해야
수정이 적용된다. 테스트는 별도 최신 소스 인스턴스에서 수행했다.
