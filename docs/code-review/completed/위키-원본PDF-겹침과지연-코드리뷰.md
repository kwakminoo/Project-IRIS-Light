# 위키 원본 PDF 패널 — 겹침·지연 코드리뷰

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-20261020-WIKI-ORIG |
| 작성일 | 2026-10-20 |
| 관련 | `iris/ui/workspaces/obsidian_workspace_page.py`, `iris/knowledge/wiki_original.py`, `iris/ui/qt_bootstrap.py` |
| 대상 | 위키 노트 오른쪽 미리보기의 요약·원본 PDF 표시 |
| 목적 | 겹침 원인·레이아웃 계약·PDF 지연 원인·최적화 빈자리를 고정한다 |

## 1. 결론

하단 PDF 영역은 **랜딩 페이지가 아니다.** 코드·UX 이름은 **원본 패널**(또는 **원본 문서 미리보기**, objectName `WikiOriginalPane`)이 맞다. 웹의 landing page는 사이트 첫 화면을 뜻한다.

겹침은 요약(`QTextBrowser`)과 원본(`QWebEngineView`)을 **세로 `QSplitter`로 나란히 둔 뒤**, Windows에서 Chromium **네이티브 HWND**가 형제 위젯 위로 그려지면서 생겼다. 요약 위·원본 아래가 레이아웃 의도였으나, 스플리터 높이 0·재배치 순간에 기하가 겹치면 본문과 PDF가 같은 화면에 포개진다.

지연의 주원인은 UI 버그가 아니라 **전체 Chromium(WebEngine)으로 PDF를 여는 비용**이다. 첫 `QWebEngineView` 생성은 이미 `qt_bootstrap`이 「수십 초 UI 블록」을 경고하는 경로와 같고, 노트 전환마다 `view.load(file://…pdf)`로 문서 전체를 Chromium PDF 뷰어에 넘긴다. 한글 경로면 `viewer_local_path`가 TEMP 복사를 한 번 더 한다.

이번 세션에서 **겹침은 VBox(요약 → 캡션「원본 문서」→ 원본 패널)로 고쳤다.** 아래 개선안은 지연·체감 속도용이며, 아직 전부 않았다.

## 2. 확인한 사실

| 사실 | 근거 |
|---|---|
| 노트 본문은 마커·`## 원본`을 잘라 위쪽만 HTML로 그린다 | `split_note_view` → `render_wiki_document` |
| PDF 바이트는 노트 옆 `worig-*.assets/original.pdf` | `store_original` / `require_original` |
| 미리보기는 `QWebEngineView.load(local file)` + fragment `view=FitH` | `_load_original` |
| WebEngine은 기동 시 만들지 않고 첫 사용 시 만든다 | `qt_bootstrap.py` 주석, `_ensure_original_view` |
| 비ASCII 경로는 TEMP로 복사한다 | `viewer_local_path` |
| 초파리 논문 노트 예 | `~/.iris-light/iris-wiki/research/agents/초파리-뇌-발화-연산-커넥터-논문.md` |
| pymupdf는 추출·OCR·내보내기에만 쓰이고, 위키 미리보기에는 안 쓴다 | `content_extract` / `pdf_export` |

## 3. 구조

요청이 화면까지 가는 길. **이번 겹침·지연은 오른쪽 미리보기 가지에서 갈라진다.**

```
그래프 노드 클릭 / 검색 활성화
  └─ ObsidianWorkspacePage.show_note(rel)
       ├─ IrisWiki.read_note
       ├─ split_note_view  →  (요약 md, iris-original 상대경로)
       ├─ render_wiki_document → QTextBrowser(_body)          ← 위: AI 요약
       └─ asset 있으면
            ├─ _reveal_original_pane  (캡션 + WikiOriginalPane 표시)
            └─ QTimer(0) → _load_original
                 ├─ viewer_local_path  (비ASCII면 TEMP 복사)
                 └─ QWebEngineView.load(file://…/original.pdf)  ← 아래: 원본 패널
                      └─ Chromium 내장 PDF 뷰어 (전체 문서)
```

겹침이 나던 분기(수정 전): `_body`와 `_original_slot`이 **세로 QSplitter** 자식 → HWND 겹침.  
수정 후: `WikiNoteColumn` VBox — `_body`(stretch 1) → `_original_cap` → `_original_slot`(stretch 2).

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 막지 못한 / 느린 이유 |
|---|---|---|
| `show_note` | 요약 HTML과 원본 경로를 나눔 | 레이아웃 계약을 스플리터에 맡김 |
| `_reveal_original_pane` (구) | `setSizes`로 칸을 열려 함 | 높이 0·재진입 시 기하가 불안정. WebEngine HWND clip 보장 없음 |
| `_ensure_original_view` | 첫 PDF에서 Chromium 뷰 생성 | 생성 자체가 무거움 (부트스트랩이 이미 경고) |
| `_load_original` | 로컬 PDF URL 로드 | 페이지 단위가 아니라 **파일 전체**를 Chromium에 넘김. 동일 URL 재로드도 가능했음 |
| `viewer_local_path` | 한글 경로 우회 복사 | 큰 PDF면 디스크 I/O가 체감 지연에 가산 |
| `qt_bootstrap` / Chromium flags | GPU 합성 끄기 등 공유 스택 안정화 | IDE·메일·위키 원본이 **한 Chromium 스택**을 공유 → 경합 가능 |
| `wiki_original.compose_wiki_body` | md에 요약·원본 텍스트 구조 | UI 원본 패널과는 별개. 미리보기 속도에 직접 관여 안 함 |

하지 않은 일: 그래프·저장 import·OCR·요약 모델 경로. 이번 증상과 무관하다.

## 5. 개선안

구조에서 빈 자리만.

| 우선 | 빈 자리 | 방향 |
|---|---|---|
| P0 | 겹침 | **완료:** VBox로 요약 아래 원본 패널 고정. 캡션 「원본 문서」 |
| P1 | 첫 표시 체감 | **완료:** 「불러오는 중…」 → PDF 미리보기 완료 / WebEngine `loadFinished` 후 숨김 |
| P1 | 첫 페이지 즉시 | **완료:** `first_page_png`(pymupdf) → `QLabel`. 「전체 보기」에서만 WebEngine |
| P2 | 재진입 | **완료:** `_previewed_original` / `_loaded_original`로 동일 원본 재로드 생략 |
| P2 | TEMP 복사 | **완료:** `viewer_local_path` size·mtime 캐시. assets는 기존 `worig-*.assets` ASCII |
| P3 | 엔진 교체 | `QPdfView`(Qt PDF) 또는 외부 기본 PDF 앱 버튼. WebEngine PDF 플러그인 경로 폐기 검토 — **미실시** |
| P3 | 프리웜 | 위키 탭 첫 진입 idle에 숨은 `QWebEngineView` 1회 생성(메인 기동에는 금지) — **미실시** |

권장 순서: P0(레이아웃) → P1 플레이스홀더 + pymupdf 1페이지 → 필요 시 P3 엔진 교체. P0~P2 반영 완료.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| Chromium / PDFium (Qt WebEngine) | 현행 전체 PDF UI | 무거움이 지연 원인. 유지하되 1차 페인트만 가볍게 |
| PyMuPDF (이미 의존) | `page.get_pixmap` → 썸네일/1페이지 | 레이아웃 수정만으로 겹침을 먼저 닫음 |
| Qt PDF (`QPdfView` / `QPdfDocument`) | 경량 내장 뷰어 | PyQt6 휠·패키징에 모듈 포함 여부 확인 필요. 조사는 했으나 이번 패치에 넣지 않음 |
| pdf.js (Mozilla) | WebEngine 안에서 JS 뷰어 | 여전히 WebEngine 기동 비용. 로컬 file 제약 |
| SumatraPDF / OS 연결 프로그램 | 「외부로 열기」 | 인앱 미리보기 요구와 다름. 보조 버튼용 |
| Obsidian PDF embed | 노트 스크롤 안 임베드 UX 참고 | Windows에서 WebEngine을 같은 스크롤에 넣으면 HWND가 스크롤을 따라가지 못함 → **같은 스크롤 임베드는 비추천** |

## 7. 조치

1. 레이아웃을 VBox로 바꿔 원본 패널이 요약 **아래**만 쓰게 함 (`WikiOriginalPane`).
2. PDF는 pymupdf 1페이지 미리보기 + 「전체 보기」에서만 WebEngine.
3. 「불러오는 중…」 플레이스홀더, TEMP size·mtime 캐시, 동일 원본 재로드 생략.
4. 검증: `python -m iris.ui._check_wiki`, `python -m iris.knowledge.wiki_original`, `unittest tests.test_wiki_original_forced`.
5. 수동: Wiki → 초파리 논문 노트 — 요약 아래 「원본 문서」에 1페이지가 바로 보이고, 「전체 보기」에서만 전체 PDF.
