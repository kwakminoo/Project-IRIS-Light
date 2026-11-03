# How: chip PDF → Hermes (lab-dump intercept)

### Overview

채팅 칩으로 PDF를 붙이면 `AttachmentWorker`가 호스트에서 본문을 뽑아 `PreparedAttachments`로 넘기고, `model_content`의 `BEGIN ATTACHMENT TEXT`만 Hermes 메시지에 실린다. 그 본문은 `AttachmentStore.prepare` → `_read`의 `MAX_CONTEXT_CHARS`(24000) 예산으로 잘리며 `truncated=true`가 자주 붙는다. 실습 전량 파일 생성은 이 발췌를 모델 컨텍스트에 넣는 경로와 분리해야 하며, 가로채기는 `prepared`가 도착한 직후·Hermes 커밋 전인 `MainWindow._continue_user_turn_bound`가 가장 안전하다.

### Key Concepts

| 개념 | 뜻 |
|---|---|
| Chip / `@` 경로 | 컴포저 첨부. `chip_fs_path`로 실제 파일 경로로 풀린다. |
| `PreparedAttachments` / `Attachment` | 앱이 이미 읽은 결과. `text`는 예산 발췌, `path`는 호스트 전용(와이어에 안 넣음; PDF는 `model_content`에 `Attachment path` 한 줄로만 노출). |
| `read_pdf_pages` | 쪽마다 글자층 → OCR → (있으면) 비전. 칩 `_parts`와 `content.extract`가 공유. |
| `MAX_CONTEXT_CHARS` (24k) | **채팅 1차 발췌** 상한. `truncated` 플래그의 주원인. 파일 바이트 한도와 별개. |
| `content.extract` / `_MAX_CHARS` (80k) | Hermes가 `truncated=true`일 때 호출하는 **재추출 도구** 경로. 여전히 전량·무제한이 아님. |
| Lab-dump intercept | 의도 감지 후 앱이 PDF를 쪽 단위로 파싱·파일 기록. 전량 본문은 Hermes messages에 넣지 않음. |

한도 계층 (정책 유지, 제거 금지):

| 상수 | 값 | 적용 지점 |
|---|---|---|
| `MAX_FILE_BYTES` | 20MB | `attachment_context._read` 진입 |
| `MAX_PDF_PAGES` | 200 | `_parts` → `read_pdf_pages(page_limit=…)` |
| `VISION_PAGE_CAP` | 4 | `read_pdf_pages` (비전 배치; `vision_all` 아니면) |
| `MAX_CONTEXT_CHARS` | 24000 | `AttachmentStore.prepare` 잔여 예산 → `_read(…, budget=…)` → `item.truncated` / `item.text[:budget]` |
| `content_extract._MAX_CHARS` | 80000 | `content.extract` / `extract_*` 도구 응답 `_truncate` |

### How It Works

```
칩 PDF + 사용자 문장
  → MainWindow._execute_user_turn_body
  → AttachmentWorker.run
       → prepare_attachments → AttachmentStore.attach / prepare
            → read_attached_file → _read(budget ≤ 24k)
                 → _document_chunks ← _parts(pdf)
                      → read_pdf_pages(page_limit=200, vision_reader=…)
                 → 쿼리 점수 청크 선별, truncated = (total>budget | count>selected)
  → prepared 시그널
  → _continue_user_turn → _continue_user_turn_bound
       → (UI) truncated 알림
       → ★ lab-dump intercept 후보 (여기)
       → _commit_recorded_user_turn(model_content=prepared.model_content(text))
            → history.model_content = BEGIN ATTACHMENT TEXT + metadata(truncated=…)
  → Hermes/Ollama 요청
       → _chat_messages_with_project_context → inference_messages(history)
            → wire content = model_content || content
```

1. **칩 수집** — 턴의 `turn.attachments`와 세션 `AttachmentStore.roots`가 있으면 워커 경로로 간다 (`main_window` ~4887).
2. **오프-GUI 추출** — `AttachmentWorker`가 비전용 `image_reader`를 바인딩한 뒤 `prepare_attachments` 호출.
3. **예산 분할** — `store.prepare`가 `remaining = MAX_CONTEXT_CHARS`에서 폴더 목록·후보 파일에 `per_file` 예산을 나눈다. PDF 한 장이면 거의 전부(~24k)가 그 파일 예산.
4. **PDF 본문** — `_parts`가 `read_pdf_pages`로 쪽 텍스트를 만들고, `_read`가 3k 청크를 쿼리(`query_terms` / `prefers_document_tail`)로 순위 매겨 예산 안만 `item.text`에 남긴다. `truncated=true`면 UI 알림 + metadata.
5. **모델 문장** — `PreparedAttachments.model_content(question)`이 인덱스·metadata·`BEGIN ATTACHMENT TEXT`·(PDF면) `Attachment path`·질문 복제를 한 문자열로 만든다. 디스플레이 `content`와 분리된 `model_content`로 히스토리에 기록.
6. **Hermes** — `inference_messages`가 `model_content`를 우선해 wire messages를 만든다. 시스템 쪽에 truncated면 `content.extract`를 쓰라는 지침이 있다 (`_chat_messages_with_project_context`, `hermes_memory_nudge` 15e).
7. **오늘 실패 모드** — 강의 PDF 전량이 24k를 넘으면 Hermes는 부분 본문만 보고 붙여넣기를 요구하거나, `content.extract`(80k)로 재시도해도 「모든 실습 파일」에는 부족할 수 있다.

**Intercept (앱 소유 lab-dump, 한도 유지):**

- 지점: `_continue_user_turn_bound`, `prepared is not None`이고 추출 텍스트가 있을 때, `_commit_recorded_user_turn(..., model_content=prepared.model_content(...))` **호출 전**.
- 이유: 이미 PDF `Attachment.path`와 사용자 질문이 있고, 아직 24k 발췌가 Hermes 히스토리에 고정되기 전이다. 글로벌 한도를 풀지 않고, dump 모듈이 `read_pdf_pages`를 **별 경로**로 쪽 단위 소비 → 라벨 파싱 → `write_project_file`만 수행하면 된다.
- Hermes에는 쓴 경로 요약만 넣거나, 고정 Iris 답으로 턴을 끝내고 에이전트 호출을 생략한다. `prepare_attachments` / `MAX_CONTEXT_CHARS`는 그대로 둔다.

### Where Things Live

| 역할 | 파일 · 심볼 |
|---|---|
| 한도·`_read`·`model_content`·`inference_messages` | `iris/runtime/attachment_context.py` |
| 예산 분할·폴더 후보 | `iris/runtime/attachment_store.py` (`prepare`, `read_attached_file`) |
| PDF OCR/비전 | `iris/knowledge/content_extract.py` (`read_pdf_pages`, `_MAX_CHARS`, `VISION_PAGE_CAP`) |
| 워커 스레드 | `iris/ui/workers/attachment_worker.py` (`AttachmentWorker`) |
| 턴 연결 · **intercept** | `iris/ui/window/main_window.py` (`_continue_user_turn_bound`) |
| Hermes wire | 동 파일 `_chat_messages_with_project_context` + `inference_messages` |
| 에이전트 재추출 힌트 | `iris/system/hermes_memory_nudge.py` (15e); MCP `content.extract` (`control_actions/wiki.py`) |
| 프로젝트 파일 쓰기 | `iris/system/project_ops.py` (`write_project_file`) |
| 칩 PDF 회귀 검사 | `iris/ui/_check_chip_pdf_enrich.py` |
| 신규 dump (예정) | `iris/knowledge/lab_script_dump.py` — pure parse+dump; UI는 thin hook만 |

### Gotchas

- **잘림 ≠ 파일 크기.** 2.9MB PDF도 20MB 안이면 통과한다. 채팅에서 잘리는 것은 글자 예산(24k)이다.
- **`content.extract`는 lab-dump가 아니다.** 80k·페이지 한도가 남고, 결과는 다시 모델 컨텍스트로 들어간다. 전량 실습 쓰기의 대체재로 쓰지 말 것.
- **하이브리드 슬라이드**(제목 글자층 + 코드 이미지): 글자층이 짧으면 OCR/비전으로 넘어간다. 비전은 기본 `VISION_PAGE_CAP`(4)장.
- **「마지막」「7-7」** 은 `_read` 청크 선별(`prefers_document_tail` / `query_terms`)에만 유리하다. 「전부 / 모든 실습」은 선별이 약해 truncated 발췌로 Hermes가 막히기 쉽다.
- **`Attachment.path`는 payload에서 빠지지만** PDF/이미지 `model_content`에는 `Attachment path:` 절대경로가 한 줄 들어간다(재추출용). Lab-dump는 그 경로 또는 `prepared.attachments[].path`를 쓰면 된다.
- **Intercept를 `prepare_attachments` 안으로 넣지 말 것.** 한도·발췌 계약을 깨기 쉽고, 프로젝트 루트·턴 종료·Hermes 생략은 UI/런타임 책임이 맞다.
