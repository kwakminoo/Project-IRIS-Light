# 채팅 GPT식 전사 — B0 bakeoff 승자

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-20261117-B0WIN |
| 작성일 | 2026-11-17 |
| 관련 | `채팅-GPT식전사-구현로드맵-핸드오프-2026-11-17.md`, scratch `docs/code-review/scratch-b0-gpt-transcript/` |
| 대상 | H1(WebEngine 전사) vs H2(위젯 리스트) |
| 목적 | B0 승자 1개와 짧은 근거. T0 구현은 포함하지 않음 |

## 1. 결론

**승자: H1 — 단일 `QWebEngineView` 전사.**  
동일 샘플에서 writing 편집, Code/Preview 전환, 인라인 계산기는 H1·H2 모두 통과했다.  
GPT식 목표(브라우저급 타이포·여백, 인라인 Preview/앱, 이후 CodeMirror류)에 맞는 확장 축은 H1 한 문서 DOM이다. H2는 파트마다 WebEngine를 쌓아 Chromium 비용은 커지고, 풍부 MD는 다시 웹으로 밀린다.

프로토타입은 throwaway다. 본 구현은 다음 세션 **T0**부터.

## 2. 확인한 사실

| 항목 | 결과 | 근거 |
|---|---|---|
| 동일 샘플 | writing / code HTML / 인라인 계산기 한 턴 | `scratch-b0-gpt-transcript/shared/sample_turn.json` |
| H1 3체크 | PASS | 메인 재실행 `run.py --verify` → `ok: true` |
| H2 3체크 | PASS | 메인 재실행 `run.py --check` → `PASS` |
| H1 산출 | 한 Chromium 페이지 + 중첩 iframe | `h1-webengine/run.py`, `NOTES.md` |
| H2 산출 | `QScrollArea` + 파트 위젯, Preview·앱은 각각 WebEngine | `h2-widget-list/run.py`, `NOTES.md` |

## 3. 비교 (루브릭)

| 기준 | H1 | H2 | 판단 |
|---|---|---|---|
| Writing 편집 | contenteditable | `QPlainTextEdit` | 동점 |
| Code / Preview | DOM 탭 + iframe | `QTabWidget` + WebEngine | 동점 |
| 인라인 계산기 | 턴 안 iframe | 턴 안 WebEngine | 동점 |
| 풍부 레이아웃 (T2 완료 기준) | 페이지 CSS로 확장 | QLabel·QSS 한계, 풍부 MD면 WebEngine 추가 | **H1** |
| Chromium 수 | 전사 1 + iframe(문서 내부) | code Preview·app마다 `QWebEngineView` | **H1** (긴 대화) |
| Iris 기존 패턴 | App Host·IDE와 같은 WebEngine+브리지 | 네이티브 스크롤·드롭은 유리 | 셸은 Qt 유지, 전사만 H1 |
| T2 이후 (에디터·앱·스트림) | DOM/JS 한 호스트에 붙이기 | 위젯·WebView 높이·가상화 부담 | **H1** |

## 4. H2에서 가져오지 않는 것 / 남는 주의

| 항목 | 내용 |
|---|---|
| 가져오지 않음 | H2를 기본 전사 호스트로 두지 않음 |
| 남는 주의 | Companion 드롭·frameless·슬롯 abort는 **창 셸(Qt)** 계약. H1이어도 전사를 frameless 자식 모달에 붙이지 말 것 |
| H1 위협 | nested iframe sandbox/CSP, writing→저장은 `QWebChannel` 등으로 브리지 |
| 폐기 | H3(QTextEdit+커스텀 object)는 로드맵대로 비추천 유지 |

## 5. 조치

1. 로드맵 B0를 **H1 승**으로 닫는다. 다음 세션은 **T0** (`MessagePart` frozen types + serde + 표시용 MD 요약, UI 없음).
2. scratch 프로토타입은 참고용으로 두고, production `iris/`에는 아직 올리지 않는다.
3. T2에서 H1 빈 전사 + text part만 붙일 때 App Host와 같은 `ensure_qt_webengine_ready`·브리지 패턴을 재사용한다.
