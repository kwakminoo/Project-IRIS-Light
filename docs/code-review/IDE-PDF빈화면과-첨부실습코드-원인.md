# IDE PDF 빈 화면 · 첨부 PDF 실습코드 「이미지라 불가」

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-PDF-VIEW-CODE |
| 작성일 | 2026-10-27 |
| 관련 | IDE-마켓플레이스설치-핀만되고-뷰어미적용-원인, 자료인지-PDF읽기실패-원인과-개선안, 파일생성-말로만완료-원인 |
| 대상 | (1) IRIS IDE에서 PDF를 열면 내용이 안 보임 (2) 채팅에 PDF 첨부 후 실습 코드 생성이 「이미지라서 불가」 |
| 목적 | 두 증상의 갈림과 개선 순서를 고정한다 |

## 1. 결론

두 증상은 **같은 버그가 아니다.**

| 증상 | 1차 원인 |
|---|---|
| IDE에서 PDF가 안 보임 (또는 깨짐) | **확장은 올라간다.** `plugin.loaded=true` (2026-10-27 실측). 그런데 활성 탭은 Monaco 텍스트 에디터라 `%PDF-1.5` 바이너리만 보인다. `pdf.view` 커스텀 에디터 위젯은 생기지만 `lm-mod-hidden`이고 iframe이 비어 페이지가 안 그려진다. 브리지 `openInEditor`는 `openerService.open` 뒤에 `editorManager.open`으로 Monaco를 또 켠다 |
| 첨부 PDF → 「실습코드가 이미지라 불가」 | **칩 첨부 PDF는 AttachmentWorker가 pypdf 글자 층만 읽는다.** OCR·비전 있는 `read_pdf_pages`는 칩이 있으면 건너뛴다. 제목만 있으면 모델이 「코드는 이미지」라고 하고, 글자가 전혀 없으면 OCR 미지원으로 거절한다 |

채팅에 OCR·비전 파이프는 이미 있다. 다만 칩 첨부 경로가 그걸 안 탄다.  
IDE는 Open VSX `mathematic.vscode-pdf`에 의존한다. **미설치가 아니다.** 열린 뒤 Monaco가 앞을 차지하고, 커스텀 웹뷰는 껍데기만 있다.

## 2. 확인한 사실

| 사실 | 근거 | 판정 |
|---|---|---|
| 2026-10-27 Theia에서 PDF 실측 | `IrisIdeRuntimeManager.start` + 브라우저로 `127.0.0.1:<theia>` 로드. `A Practical Tutorial on Agentic AI.pdf` 열림 | measured |
| `mathematic.vscode-pdf` loaded true | 브리지 `pluginLoaded` → `{loaded: true, via: theia}` | measured |
| 활성 위젯은 Monaco | DOM id `code-editor-opener:file://...pdf`, 본문 `%PDF-1.5` + FlateDecode 바이너리. 스크린샷 동일 | measured |
| 커스텀 에디터 위젯은 숨김·빈 껍데기 | id `plugin-custom-editor:file://...pdf`, class `theia-webview lm-mod-hidden`, 자식은 overlay만, iframe 없음 | measured |
| Theia 로그도 텍스트로 연 흔적 | `contains one or more unusual line terminator characters` (해당 PDF) | measured |
| 확장 engines는 `^1.134.0`, Theia API는 `1.130.0` | package.json / `@theia/application-package` `DEFAULT_SUPPORTED_API_VERSION` | measured |
| `openInEditor`가 Monaco를 강제 | `iris-ide-bridge-poller.ts` `openerService.open` 다음 `editorManager.open` | measured |
| 예전 `marketplace_install`은 핀만 함 | `completed/IDE-마켓플레이스설치-핀만되고-뷰어미적용-원인.md` | measured (과거) |
| 지금은 VSIX를 `deployedPlugins`에 품 | `project_marketplace.install_extension`, `ide.marketplace_install` | measured |
| 성공 조건은 `package.json` + `plugin.loaded` | 넛지 15f, 액션 summary | measured |
| 글자 층 ≥ 40자면 그 쪽은 OCR·비전 생략 | `content_extract._LAYER_MIN = 40` | measured |
| 비전은 최대 4쪽 묶음 | `VISION_PAGE_CAP = 4` | measured |
| 칩 첨부 시 AttachmentWorker가 먼저 돈다 | `main_window` `if turn.attachments` → AttachmentWorker | measured |
| 그 뒤 `prepared is not None`이면 MaterialRead를 안 탐 | `_continue_user_turn_bound` | measured |
| 칩 PDF는 pypdf만. 스캔이면 OCR 미지원 거절 | `attachment_context._parts` | measured |
| MaterialRead/`[자료 본문]`은 칩 없을 때(@경로 등) | `_start_material_read` | measured |
| 넛지 15e는 `[자료 본문]`이 있을 때만 캡처 요구 금지 | `hermes_memory_nudge` | measured |
| 강의 PDF 글자 층은 제목만 (실습 코드 없음) | 사용자·Iris 대화 (컴퓨터비전_05) | measured (대화) |

## 3. 구조

### 3.1 IDE에서 PDF 열기

```
탐색기 더블클릭 / ide.open_file / 브리지 openFile
  → IrisIdeBridgePoller.openInEditor
        → openerService.open(uri)     ← 커스텀 에디터 후보
        → editorManager.open(uri)     ← Monaco 텍스트 강제 (라인/컬럼용)
  → PDF 확장 없음
        → 바이너리를 Monaco에 → 빈/깨진 탭
  → PDF 확장 loaded + customEditor pdf.view
        → 그래도 Monaco 강제면 뷰어를 덮을 수 있음
```

설치 경로 (현재 코드).

```
ide.marketplace_install(id)
  → pin + VSIX → ~/.iris-light/iris-ide/user-data/deployedPlugins/<id>/
  → reload → plugin.loaded
```

갈림.

- 번들 `plugins`에 PDF 없음 (builtin만).
- `package.json` 있어도 `plugin.loaded` false면 뷰어 없음.
- `mathematic.vscode-pdf`의 `engines.vscode`가 Theia보다 높거나 browser/webview 경로가 안 맞으면 활성화 실패 가능.
- 위키 `QWebEngineView` PDF 보기와 IDE Theia 탭은 **별 경로**.

### 3.2 채팅 PDF 첨부 → 실습 코드

```
칩으로 PDF 첨부 + 「실습코드로 스크립트 만들어」
  → AttachmentWorker → attachment_context._parts(.pdf)
        ├─ pypdf에 글자 있음 → 제목·설명만 모델에 전달 (코드 그림 미읽음)
        │     → Hermes: 「코드는 이미지라 불가/캡처」  ← 흔한 체감
        └─ pypdf에 글자 없음 → "스캔 PDF… 채팅 PDF OCR은 지원하지 않습니다"
              → 모델 미호출, 거절 문구만

MaterialRead / read_pdf_pages (OCR·비전)  ← 칩이 있으면 이 갈래를 안 탐
  → @경로만 있거나 prepared is None 일 때만
```

1차 갈림은 Hermes가 아니라 **칩 첨부 = AttachmentWorker(구형 pypdf)** 이다.  
저장소 안의 OCR·비전은 위키·MaterialRead에만 연결되어 있다.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 요청을 막지 못한 이유 |
|---|---|---|
| Theia / `openInEditor` | Monaco `editorManager.open` 강제 | 번들 PDF 없음 + 확장 있어도 커스텀 에디터를 덮을 수 있음 |
| `ide.marketplace_install` | VSIX 배포까지는 함 | loaded false / engines·webview 비호환이면 빈 탭 |
| Wiki Chromium PDF | 별도 창에서 렌더 가능 | IDE 탭과 공유하지 않음 |
| `AttachmentWorker` / `_parts` PDF | pypdf만. 스캔은 즉시 거절 | 칩 첨부 실습 PDF의 본선. OCR·비전 미연결 |
| `_continue_user_turn_bound` | prepared 있으면 MaterialRead 스킵 | 같은 PDF라도 칩 vs @경로가 다른 품질 |
| `read_pdf_pages` (Material/위키) | 글자 층 ≥40자면 OCR·비전 생략 | 칩을 고쳐도 제목만 긴 슬라이드는 코드 그림을 스킵할 수 있음 |
| `VISION_PAGE_CAP=4` | 이미지 쪽 일부만 비전 | 실습이 여러 쪽이면 부족 |
| 넛지 15e | `[자료 본문]` 있을 때만 캡처 금지 | 칩 경로는 `[자료 본문]`이 안 붙어 15e가 안 먹음 |

하지 않은 일.

- IDE에 PDF.js를 내장하는 것.
- 슬라이드 PDF에 「코드 그림 쪽」을 강제 OCR하는 휴리스틱.

## 5. 개선안

### 5.1 2026-10-27 병렬 테스트 (새 채팅)

| 테스트 | 결과 | 한 줄 |
|---|---|---|
| A Monaco skip + `pdf.view` | PARTIAL | 커스텀 위젯·iframe은 뜸. iframe=`about:blank#blocked`, `*.webview.127.0.0.1` DNS 실패 → 페이지 없음 |
| B 구버전 `vscode-pdf@0.1.11` | FAIL | engines 호환해도 iframe 본문 빈 껍데기. 마켓 확장 경로로는 페이지 미확인 |
| C Iris PDF.js 스파이크 | PARTIAL(렌더 PASS) | vendor pdf.js로 오프라인 페이지 렌더 성공. Theia OpenHandler+번들은 미배선 |
| D Iris 조작/검증 | — | IDE `opened`/`visible`/`loaded` ≠ 페이지 보임. Wiki WebEngine만 실제 렌더. verify 신호 없음 |

### 5.2 권장 구현 순서 (IDE PDF)

| 순위 | 제안 | 이유 | 완료 기준 |
|---|---|---|---|
| **P0** | **A4** Iris 소유 `IrisPdfOpenHandler` + vendored PDF.js 위젯 | A·B가 마켓 `pdf.view` 웹뷰 호스트에서 막힘. C만 페이지 렌더를 증명 | IDE 탭에 페이지 캔버스. Open VSX 불필요 |
| **P0** | `openInEditor`에서 `.pdf`는 Monaco `editorManager.open` 생략 | A에서 바이너리 탭 제거에 필요. C 위젯과 함께 | `%PDF` Monaco 탭 없음 |
| **P1** | 브리지 성공 신호 `viewer: "iris.pdf" \| "monaco" \| "none"` + Hermes 「페이지 보임」은 `viewer==iris.pdf`만 | D 계약. `opened:true` 허위 금지 | 바이너리/빈 탭을 성공으로 안 말함 |
| **P2** | (단기 우회) 채팅 「PDF 보여줘」→ Wiki import/open, 문구는 「위키에 열었다」만 | D: 오늘 페이지를 그리는 유일한 제품 경로 | 시각 완료 단정 금지 |
| ~~A1~~ | 마켓 확장 설치만 | loaded=true여도 페이지 없음 (실측) | 본선에서 제외 |
| ~~A2 alone~~ | `pdf.view`만 | A·B: 껍데기만 | 본선에서 제외 |

채팅 칩(B0~B4)은 IDE 빈 화면과 별건. 기존 순위 유지.

하지 말 것.

- 모델에게 셸로 PyMuPDF 실행시키기.
- 채팅 펜스 전면 폴백 부활.
- `mathematic.vscode-pdf`를 본선 뷰어로 유지하려는 추가 패치 (웹뷰 호스트가 깨진 채).

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| PDF.js (vscode-pdf 자산에서 vendor) | `getDocument` + canvas 렌더 (C 스파이크) | 마켓 확장 런타임·customEditor 웹뷰는 가져오지 않음 |
| Theia `WidgetOpenHandler` / `IrisIdeStartWidget` 패턴 | `.pdf` OpenHandler 등록 | — |
| Wiki QWebEngine PDF | 단기 「보여주기」우회만 | IDE 탭과 공유하지 않음. 장기 본선 아님 |
| pymupdf get_text("dict") | 채팅 B1용 후보 | IDE 뷰어와 무관 |

## 7. 조치

1. IDE 본선: **P0 = A4(내장 PDF.js OpenHandler) + Monaco skip**. 그다음 P1 브리지/`viewer` 계약.
2. 마켓 `vscode-pdf`는 진단용으로만. 페이지 표시의 성공 조건으로 쓰지 않음.
3. 채팅 첨부 품질은 별도 **B0** (요청 시).
4. Computer Use 권한은 Cursor 설정/Output 수동 확인 중 (이 문서 범위 밖).
