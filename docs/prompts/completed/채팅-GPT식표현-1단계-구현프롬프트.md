# Prompt: 채팅 GPT식 matrix 격자 표시 (P0)

기준: `docs/code-review/채팅-GPT식표현-구현설계.md` 5.2 P0.

```text
Context:
- 채팅 답은 Markdown → chat_renderer → HTML → QTextEdit 이다.
- 표는 _style_tables 로 공통 셀 스타일만 입힌다. 셀 값별 배경색은 없다.
- fenced code 는 _upgrade_fenced_pre_to_cards 가 코드 카드로 바꾼다.
- 수식 $...$ 는 math_latex 가 이미 PNG 로 조판한다. 건드리지 않는다.
- P1 Vision, P2 code plot, HTML 기본 작성, WebEngine 채팅은 이번 범위가 아니다.

Goal:
1) 모델이 ```matrix 펜스로 격자를 쓰면, 코드 카드가 아니라 색 칠한 HTML 표로 보인다.
2) 셀 값이 1 이면 연파란(다크 테마용) 배경, 0 이면 대비 배경. 가운데 정렬.
3) 본문 첫 줄이 # 로 시작하면 표 위 캡션으로 쓴다.
4) Hermes MEMORY nudge 에 짧은 답변 형식 힌트를 넣는다
   (단계 헤더, ---, $수식$, 격자는 ```matrix).
5) _check_chat_blocks 에 matrix 픽스처 assert 를 두고 통과시킨다.

Constraints:
- 일반 MD 표 이진 휴리스틱은 넣지 않는다 (오탐 방지. DSL 만).
- sanitize 허용 태그를 넓히지 않는다 (table/td/th 이미 허용).
- diagram_card, project.run, attachment OCR 경로는 건드리지 않는다.
- 새 의존성 금지.

Interface / data shape:
- MatrixGrid: caption: str | None, rows: list[list[str]]
- 파서: language-matrix fenced body → MatrixGrid
  행 구분 줄바꿈, 셀 구분 공백 또는 콤마. 빈 줄 무시.
- 렌더: <table data-iris-matrix="1"> + td data-iris-matrix-cell + inline background
  _style_table_cell 이 붙인 스타일보다 셀 배경이 살아남게
  (_merge_cell_style 는 existing 이 뒤라 background 가 유지됨).
- theme_tokens: chat_matrix_one_bg / chat_matrix_zero_bg
  (및 필요 시 fg). GPT 연파란을 다크 채팅에 맞게.
- hermes_memory_nudge: 마커 v22, matrix 형식 한 절. ensure 조건에 새 문자열 추가.

TDD:
1) _assert_matrix_fence 를 먼저 추가하고 자검을 돌려 RED 를 확인한다.
2) 구현 후 같은 자검이 GREEN.
3) 기존 prose/fenced/wiki 스모크가 깨지지 않는다.

검증:
.venv\Scripts\python.exe -m iris.ui.chat._check_chat_blocks

완료 기준:
- 아래 Markdown 을 render_iris_message 에 넣으면
  중앙 1 셀 HTML 에 chat_matrix_one_bg 색이 있고,
  코드 카드(Python/복사)로 바뀌지 않는다.

## 1단계. 침식(Erosion)

```matrix
# 침식 결과
0 0 0 0 0
0 0 0 0 0
0 0 1 0 0
0 0 0 0 0
0 0 0 0 0
```
```
