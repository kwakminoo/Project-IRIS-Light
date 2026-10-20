# 채팅 GPT식 표현 — 구현 설계 보고서

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-20261019-GPTUI |
| 작성일 | 2026-10-19 |
| 관련 | 모폴로지 문제 스크린샷(Iris vs ChatGPT), `docs/code-review/이미지인식-채팅첨부-원인.md` |
| 대상 | 채팅 답변의 표·수식·격자·실행 플롯 표시 |
| 목적 | 구현 전에 경로·단계·차용·비범위를 고정한다 |

## 1. 결론

GPT처럼 보이게 하는 핵심은 **이미지 생성(DALL·E)도, 채팅 엔진을 WebEngine으로 바꾸는 것도 아니다.**  
작성은 Markdown을 유지하고, 렌더러가 격자를 색칠하며, 필요 시 로컬 Python이 PNG를 만들어 답에 붙인다.

| 판단 | 내용 |
|---|---|
| 채택 | GPT식 표현 (P0 표시 → P1 Vision → P2 코드 플롯) |
| 보류 | 채팅 본문 HTML 기본 작성, WebEngine 전면 교체(C단계) |
| 근거 | 표시 병목은 Qt HTML 부분집합·후처리 부재·Vision/OCR·실행 PNG 회수. 작성 언어를 HTML로 바꿔도 Qt 상한은 그대로다 |

완료 기준(동일 첨부·프롬프트): 단계 헤더 + LaTeX 수식 + `1` 칸이 파란 5×5 격자. (선택) 실행 PNG가 답 안에 인라인.

## 2. 확인한 사실

| 사실 | 근거 |
|---|---|
| 채팅은 이미 MD→HTML→`QTextEdit` | `iris/ui/chat/chat_renderer.py` |
| 표 셀 공통 스타일은 있으나 값별 배경색 없음 | `_style_table_cell` |
| 수식 `$…$`/`$$…$$`는 PNG로 조판 | `iris/ui/chat/math_latex.py` |
| 복잡한 다이어그램은 로그 밖 카드 | `diagram_card.py`, archify |
| 첨부 이미지는 OCR/텍스트 추출 위주 | `attachment_context._ocr_image`, CR-IMG 보고서 |
| Hermes 켜짐 시 이미지→코드 파이프가 갈라짐 | `이미지인식-채팅첨부-원인.md` |
| `project.run`은 IDE 터미널용. 채팅 PNG 회수 계약 없음 | `control_actions/project.py` |
| Qt rich text는 HTML 4 부분집합. 둥근 버블 CSS 등 제한 | 코드 주석, Qt `QTextEdit` 문서 |
| sanitize가 `svg`/`script`/`style`/`iframe`/`math` 드롭 | `_DROP_WITH_CONTENT` |

## 3. 구조

요청이 화면까지 가는 경로. 이번 GPT식 작업이 갈라지는 지점을 `★`로 표시한다.

```text
[첨부 이미지 + 사용자 문장]
        │
        ▼
MainWindow 첨부 분기
   ├─ OCR / AttachmentWorker
   │     └─ attachment_context._ocr_image
   │           ├─ (있으면) vision reader
   │           └─ Tesseract OCR
   │     ★ P1: 격자 구조화 JSON 또는 VLM 픽셀 경로
   └─ Hermes / 로컬 턴
        │
        ▼
모델 답변 (Markdown + 선택 tool)
   ├─ ★ P0: ```matrix / MD 표 + $수식$ + 단계 헤더
   └─ ★ P2: chat.exec_python → PNG 파일
        │
        ▼
chat_panel → render_iris_message
        │
        ▼
chat_renderer._markdown_body_to_html
   ├─ stash/restore math_latex
   ├─ python-markdown (tables, fenced_code)
   ├─ _sanitize_chat_html
   ├─ ★ P0: matrix / 이진 표 셀 색칠 후처리
   ├─ fenced → 코드 카드
   └─ _style_chat_html (기존 표·hr·제목)
        │
        ▼
QTextDocument / QTextEdit 표시
   └─ (P2) <img src="iris-image:…"> 또는 허용 로컬 plot URL
```

| 갈래 | 쓰는 경우 | 산출 |
|---|---|---|
| A. Rich text | 교재형 단계·색 격자·수식 | HTML 표 (렌더러 생성) |
| B. Code artifact | 분석 플롯·큰 시각화 | PNG + img 태그 |
| C. Diagram card | archify급 다이어그램 (기존) | 로그 밖 WebView 카드 — **이번 범위 외 유지** |

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | GPT식을 막지 못한 이유 |
|---|---|---|
| `attachment_context._ocr_image` | 글자 추출 | 5×5·커널 위상 소실 → 잘못된 0배열 |
| Hermes 첨부 분기 | 경로/메타만 넘기는 경우 | 픽셀·구조 JSON이 프롬프트에 없음 (CR-IMG) |
| 모델 답변 계약 | 자유 Markdown | matrix DSL·시각화 도구 지시 없음 |
| `chat_renderer._style_tables` | 헤더/본문 공통 스타일 | 셀 값 `1`/`0` 분기 없음 |
| `math_latex` | 수식 PNG | 이미 동작 — **유지** |
| `diagram_card` | 별도 카드 | 인라인 교재 격자와 경로가 다름 — **이번엔 확장하지 않음** |
| `project.run` | IDE 실행 | stdout/figure를 채팅 버블에 안 붙임 |

### 하지 않은 일 (의도적 비범위)

- 채팅 작성 언어를 HTML 기본으로 전환
- 채팅 로그 전체를 WebEngine으로 교체 (C단계)
- DALL·E류 이미지 생성으로 0/1 격자 그리기
- `QTextEdit` 안에 WebView 삽입 (기존 diagram 계약 위반)

## 5. 개선안 (구현 방식)

### 5.1 원칙

| 원칙 | 내용 |
|---|---|
| 작성 | Markdown (+ 작은 DSL). HTML은 렌더 타깃만 |
| 표시 | 기존 `chat_renderer` 후처리 확장 |
| 수식 | 기존 `math_latex` 재사용 |
| 플롯 | 전용 도구로 PNG 생성 후 img 삽입. `project.run`과 분리 |
| 엔진 | WebEngine 전면 교체 보류 |

### 5.2 P0 — Display (1차 구현 대상)

**목표:** 모델이 올바른 숫자만 넣으면 화면이 GPT 표와 동급.

| 항목 | 설계 |
|---|---|
| DSL | fenced ` ```matrix ` (권장) 또는 일반 MD 표에 휴리스틱 |
| ` ```matrix ` 본문 | 공백/콤마 구분 행. 선택 헤더 줄 `# 침식 결과` |
| 렌더 | fence → `<table class="iris-matrix">`. 셀 텍스트가 `1`이면 연파란 배경, `0`이면 대비 배경. 가운데 정렬·고정 셀 폭 |
| 일반 표 | 열·행이 모두 `0`/`1`(또는 헤더 1행)이면 matrix와 동일 색칠 (오탐 시 DSL만) |
| 프롬프트 | Hermes nudge 또는 SOUL 보조 절: 단계 헤더(`1단계. …`), `---`, `$…$` 수식, 격자는 ` ```matrix ` |
| 자검 | `iris/ui/chat/_check_chat_blocks.py`에 matrix 샘플 HTML assert |

**건드릴 파일 (예상)**

| 파일 | 변경 |
|---|---|
| `iris/ui/chat/chat_renderer.py` | matrix fence 업그레이드, (선택) 이진 표 색칠 |
| `iris/ui/chat/_check_chat_blocks.py` | 스모크 |
| `iris/system/hermes_memory_nudge.py` 또는 짧은 포맷 스킬 | 답변 형식 지시 |
| (선택) `iris/ui/shared/theme_tokens.py` | matrix 셀 색 토큰 |

**완료 기준:** 고정 Markdown 샘플을 `render_iris_message`에 넣으면 중앙 `1` 셀에 파란 배경 스타일이 있다.

### 5.3 P1 — Vision 구조화

**목표:** OCR이 격자를 깨도 정답 입력이 산다.

| 옵션 | 내용 | 권장 |
|---|---|---|
| A | 멀티모달 모델에 이미지 바이트 전달, OCR 우회 | VLM 사용 가능 시 |
| B | `extract_binary_grid(path) → {grid, kernel, op}` JSON을 프롬프트에 주입 | 교재/시험 문제에 강함 |
| C | A 실패 → B → OCR | 기본 폴백 |

| 파일 (예상) | 변경 |
|---|---|
| `iris/runtime/attachment_context.py` | 구조화 블록 삽입 |
| 첨부 분기 (`main_window` 등) | Hermes 켜져 있어도 격자/비전 메타가 프롬프트에 들어가게 |
| (신규) `iris/knowledge/grid_extract.py` 등 | B 전용, 작게 |

**완료 기준:** 모폴로지 첨부만으로 3×3 십자 커널·중앙 3×3 전경이 JSON으로 재현된다.  
관련: CR-IMG의 Hermes 첨부 스킵·Tesseract 경로 문제는 **선행 또는 병행 수정**이 필요하다.

### 5.4 P2 — Chat code plot

**목표:** 「분석 중」급 matplotlib PNG를 답 버블에 붙인다.

```text
tool: chat.exec_python  (가칭)
  in:  code
  out: {stdout, png_paths[], error}
        │
        ▼
~/.iris-light/runtime/plots/<turn>-<n>.png
        │
        ▼
답변 HTML에 <img …> (허용 URL prefix 추가)
+ 기존 tool shell로 코드 접기
```

| 제약 | 이유 |
|---|---|
| import 화이트리스트 (numpy, matplotlib 등) | 최소 권한 |
| 네트워크 금지, 작업 디렉터리 plots만 쓰기 | 보안 |
| 타임아웃·메모리 상한, UI 스레드 밖 | freeze·qFatal 회피 |
| `project.run`과 분리 | IDE 실행 ≠ 채팅 시각화 |

**완료 기준:** 도구 호출 한 번에 채팅에 PNG가 보인다.

### 5.5 오케스트레이션 (P0 이후)

```text
첨부 + (격자|모폴로지|행렬|그래프) → P1 구조화 우선
수치 시각화 필요 → P2
그 외 → Markdown + matrix + LaTeX
금지: 생성형 이미지로 0/1 격자
```

도구 중 UI: 기존 `append_iris_tool` 칩으로 「분석 중」에 해당하는 짧은 상태만.

### 5.6 구현 순서

| 순서 | 내용 | 체감 | 난이도 |
|---|---|---|---|
| 1 | P0 matrix 렌더 + 포맷 nudge | GPT식 표 | 낮 |
| 2 | P1 Vision/격자 JSON (+ CR-IMG 경로) | 정답률 | 중 |
| 3 | P2 `chat.exec_python` + PNG | 플롯 | 중~높 |

**1차 착수 = P0만.** P1·P2는 P0 자검 통과 후.

## 6. 차용

조사한 오픈소스·패턴. 이름 / 가져올 부분 / 이번에 가져오지 않는 이유.

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| OpenAI Code Interpreter 패턴 | 실행→`image/png` 회수→메시지 첨부 흐름 | 클라우드 컨테이너 전체는 과함. P2에서 로컬 축소판만 |
| Matplotlib Annotated heatmap | `imshow` + 셀 숫자 주석, 이진 colormap | P2 플롯용 레시피. P0 표에는 불필요 |
| seaborn.heatmap | `annot=True`, `fmt="d"`, `cbar=False` | 의존 추가 회피. matplotlib만으로 동일 효과 |
| RestrictedPython | — | 문서상 샌드박스 아님. matplotlib import와 보안 경계 부적합 |
| E2B / Runtime / Podflare | microVM + matplotlib PNG 회수 UX | 외부 비용·네트워크. 1차 로컬 제한 실행 후 필요 시 |
| KaTeX / MathJax | 웹 수식 | Iris는 `math_latex` PNG 경로가 이미 있음 |
| ChatGPT 표 스타일 | `1`=연파란, `0`=밝은 칸 | UI 규칙만 모방. 프론트 스택은 Qt 유지 |
| archify / `diagram_card` | 카드 분리 패턴 | 이진 격자는 inline table이 단순. C단계 WebEngine 전면 교체와 혼동하지 않음 |
| GFM Markdown tables | 모델이 이미 잘 쓰는 표 문법 | P0에서 DSL과 병행 입력으로 유지 |
| bleach / html-sanitizer 계열 | 허용 태그 정책 참고 | 자체 `_sanitize_chat_html` 유지. 전면 교체 불필요 |
| Qt WebEngine 채팅 (C단계) | 브라우저급 CSS/SVG | 보류. GPT식 목표와 비용·안정성 불균형 |

찾지 못함: Iris QTextEdit 위에서 ChatGPT와 동일한 CSS 애니메이션·호버 격자를 주는 경량 라이브러리. (필요 시 카드형 WebView만 부분 도입.)

## 7. 위험과 완화

| 위험 | 완화 |
|---|---|
| 일반 MD 표에 색칠 오탐 | ` ```matrix ` 우선. 휴리스틱은 이진표만 |
| HTML 작성 기본화 압박 | 보고서 결론 유지. sanitize·스트리밍·모델 품질 |
| P2 `exec` 보안 | 화이트리스트·타임아웃·plots 전용. RestrictedPython에 의존하지 않음 |
| Hermes 첨부 스킵 | P1 전에 CR-IMG 분기 점검 |
| Qt 셀 `background-color` 미적용 | 자검 + 실기 스모크. 안 되면 matrix를 작은 PNG로 폴백 (math_latex와 유사) |

## 8. 검증 계획

| 단계 | 검증 |
|---|---|
| P0 | `python -m iris.ui.chat._check_chat_blocks` + matrix 픽스처 |
| P0 UI | 고정 MD를 채팅에 붙여 파란 중앙 셀 확인 |
| P1 | 모폴로지 PNG → JSON assert (단위) |
| P2 | 화이트리스트 코드 실행 → plots PNG 존재 → 렌더 img |
| 회귀 | 기존 표·코드카드·수식·diagram 카드 스모크 유지 |

## 9. 조치

1. ~~P0만 착수~~ → **완료** (`docs/prompts/completed/채팅-GPT식표현-1단계-구현프롬프트.md`)  
2. ~~P1~~ → **완료** (`…-2단계-구현프롬프트.md`, `iris/knowledge/grid_extract.py`)  
3. ~~P2~~ → **완료** (`…-3단계-구현프롬프트.md`, `chat.exec_python`)  
4. ~~P3 실전 답변 계약~~ → **완료** (`…-4단계-실전답변계약-구현프롬프트.md`): fence→matrix normalize, extract 신뢰도, nudge v24, plot merge 헬퍼  
5. HTML 기본 작성·WebEngine 채팅(C)은 열지 않았다.  
6. 자검: `_check_gpt_answer_contract`, `_check_chat_blocks` matrix, `_check_grid_extract`, `_check_chat_code_exec`  
7. 데모: `python -m iris.ui._demo_gpt_chat_viz`  
8. 확인 후 본 문서는 `docs/code-review/completed/`로 옮긴다.
