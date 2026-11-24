# IRIS 파일 첨부 파이프라인 수정·검증

검증일: 2026-10-02

## 실제 원인

첨부 UI만의 문제가 아니라 **전송 단계에서 일반 파일이 첨부 목록에서 빠지고, 남은 정보도 경로 문자열에 불과한 문제**였다.

- `ChatPanel._on_composer_drop_paths()`가 일반 파일·폴더를 표시용 `@경로`로 변환했다.
- `_emit_send()`는 일반 파일을 질문 앞의 `@경로` 문자열에 합쳤다. `send_clicked(text, attachments)`의 두 번째 인자에는 **이미지만** 넣었다.
- `MainWindow._format_user_turn_content()`도 이미지에 대해 경로 목록만 만들었다.
- `_record_history()` → `_chat_messages_with_project_context()` → `IrisAgentChatWorker` → `IrisAgentClient.stream_chat()`은 이 텍스트 히스토리를 그대로 보냈다. 파일 본문을 읽거나 추출하는 단계가 없었다.
- 기존 Wiki용 `content_extract.py`는 TXT·PDF 등을 읽을 수 있었지만 일반 채팅 첨부 경로에 연결되지 않았다. DOCX·PPTX·XLSX용 채팅 추출기도 없었다.

따라서 JSON의 `messages[].content`에 경로는 있었지만, 일반 파일은 구조화된 첨부 목록에서 빠졌고 **본문은 모든 일반 채팅 첨부에서 빠져 있었다**. 단순히 `attachments` 필드 하나를 HTTP에 추가하는 것으로 해결할 수 있는 문제가 아니었다.

## 수정 후 흐름

```text
파일 선택 / Qt Drag & Drop / Windows OLE 드롭
  → ChatPanel._on_composer_drop_paths (공통 검증, 실제 경로 유지)
  → ComposerAttachmentStrip (아이콘·파일명, 내부 경로)
  → ChatPanel._emit_send (모든 파일·폴더를 attachments로 전달)
  → MainWindow._on_user_text / UserTurnDispatcher / UserTurn
  → AttachmentWorker (Qt GUI 스레드 밖에서 파일 읽기)
  → prepare_attachments / 형식별 _parts / _office_parts
  → Attachment(id, path, filename, mime_type, size, text, error, truncated)
  → MainWindow._continue_user_turn
      화면·content: 질문 + 파일명 칩
      model_content: 질문 + 추출된 첨부 데이터 JSON
  → ChatSession / SQLite chat_messages.model_content
  → inference_messages (model_content를 실제 messages[].content로 변환)
  → Iris Agent / Ollama / OpenAI 호환 요청
  → 모델 응답
```

`Attachment.path`는 앱 내부에서만 사용한다. 모델 payload에는 `id`, `filename`, `mime_type`, `size`, `text`, `error`, `truncated`만 넣는다. 추출된 파일 본문 자체에 사용자가 작성한 경로가 있는 경우까지 지우지는 않는다.

모델에는 첨부가 앱이 이미 읽어 제공한 입력 데이터라고 설명하며, 문서 내용은 신뢰하지 않는 데이터로 취급하도록 한다. 이 설명은 **실제 본문 전달에 추가한 지침**이다.

화면 히스토리와 모델 히스토리를 따로 저장하므로 파일 본문이 채팅 UI에 펼쳐지지 않는다. 대화 복원·후속 질문에서도 저장된 본문을 사용하며 원본 파일을 다시 읽으려 하지 않는다. 기존 DB는 `model_content` 열을 추가해 마이그레이션하고 기존 메시지는 그대로 읽는다.

## 지원 형식과 제한

| 형식 | 처리 |
|---|---|
| TXT, MD, JSON, CSV, TSV | 텍스트 읽기; UTF-8/BOM, UTF-16 BOM, CP949 |
| 일반 코드·설정 파일 | PY, JS/TS, JSX/TSX, C/C++, Java, C#, Go, Rust, SQL, Shell, PowerShell, YAML, TOML 등 텍스트 읽기 |
| PDF | 페이지 번호와 텍스트 추출; 암호화·스캔 PDF는 명확한 오류 |
| DOCX | 본문·표의 문단, 머리글·바닥글 텍스트 |
| PPTX | 프레젠테이션 관계에 따른 실제 슬라이드 순서와 텍스트·표 텍스트 |
| XLSX | 실제 시트 이름·순서, 셀 주소, 공유 문자열·인라인 문자열, 캐시된 값·수식 |
| PNG, JPG/JPEG, WEBP, GIF, BMP, TIF/TIFF | Tesseract OCR. 일반 첨부는 시각 이해가 아니라 OCR 텍스트 전달 |
| 폴더 | 상대 파일 목록 + 지원하는 텍스트·문서 파일 본문 |

DOCX/PPTX/XLSX는 Python 표준 라이브러리 ZIP/XML로 처리하므로 추가 Office 라이브러리 설치가 필요 없다.

제한 정책:

- 단일 원본 파일 최대 **20 MB**. OOXML 압축 해제 크기 최대 **40 MB**.
- 첨부 본문 총 **24,000자**. 작은 파일은 전체, 큰 텍스트는 3,000자 청크를 질문 키워드로 선택한다. 문서는 페이지·슬라이드·행 단위로 읽고 한도에서 중단한다.
- 생략된 경우 `truncated=true`와 UI 안내를 표시한다. 모든 내용을 읽었다고 주장하지 않도록 모델 지침에 포함했다.
- PDF 최대 **200페이지**. 초과하면 페이지를 나눠 첨부하라고 안내한다.
- 최대 **50개 파일**, 폴더 탐색 최대 **2,000개 항목**. 폴더 목록도 본문 예산 안에서 제한한다.
- 폴더에서 `node_modules`, `.git`, `dist`, `build`, `venv`, `.venv`, `__pycache__`, `.cache`를 제외한다. 자식 심볼릭 링크·지원되는 Windows junction도 따라가지 않는다.
- 폴더 안 이미지는 자동 OCR하지 않는다. 필요한 이미지는 개별 첨부한다.
- XLSX 수식을 계산하지 않는다. 파일에 저장된 수식과 캐시값을 전달한다. PPTX 발표자 노트·도형의 시각적 배치, Office 문서에 삽입된 이미지의 의미는 추출하지 않는다.
- 스캔 PDF 채팅 OCR은 아직 지원하지 않는다. 이미지 OCR은 Tesseract와 언어 팩 설치가 필요하다. **현재 검증 환경에는 Tesseract가 없어 실제 이미지에 대해 설치 안내가 표시되는 것을 확인했다.**
- 이전 버전에서 경로만 저장한 과거 첨부 메시지는 본문을 소급 복원하지 않는다. 해당 파일은 다시 첨부해야 한다.
- 청크 선택은 키워드 방식이며 전체 문서 검색/RAG나 자동 요약은 아니다. 대화가 길어져 모델 전체 컨텍스트 한도를 넘는 문제는 기존 대화 관리 정책의 범위다.

## 실제 Iris Agent 테스트 결과

실제 TXT·PDF·PPTX 파일을 생성하고 **운영 ChatPanel, UserTurnDispatcher, MainWindow 전송 함수, AttachmentWorker**를 호출했다. IDE는 운영 `IdeCompanionPage.mount()`로 같은 채팅 위젯을 재배치했다. 추출된 운영 요청 messages를 실행 중인 로컬 Iris Agent gateway의 `IrisAgentClient.stream_chat()`에 보내 실제 응답을 받았다. 모델 선택 설정을 변경하지 않았다.

앱 전체 시작·TTS·MCP 부수 동작은 검증 harness에서 대체했다. 파일 선택은 네이티브 선택창의 결과 콜백을 호출했고, 드롭은 실제 `QMimeData/QDropEvent`로 실행했다. **사람이 Windows 탐색기를 마우스로 드래그한 수동 테스트는 아니다.** Windows OLE 경로 역시 기존 공통 첨부 진입점으로 연결되지만 이번 실측 드롭은 Qt 이벤트 경로다.

| 파일/질문 | 메인 선택 | 메인 드롭 | IDE 선택 | IDE 드롭 |
|---|---|---|---|---|
| TXT: CODE 값 | `TXT-1234` | `TXT-1234` | `TXT-1234` | `TXT-1234` |
| PDF: CODE 값 | `PDF-5678` | `PDF-5678` | `PDF-5678` | `PDF-5678` |
| PPTX: CODE 값 | `PPT-9999` | `PPT-9999` | `PPT-9999` | `PPT-9999` |
| 폴더: app.py의 CODE 값 | — | `FOLDER-7777` | — | `FOLDER-7777` |

**14/14 실제 Iris Agent 응답 통과.** 폴더의 `node_modules/ignore.txt`에 넣은 제외용 문자열이 모델 요청에 없는 것도 확인했다. 로컬 권한 없음이라는 잘못된 답변은 이 테스트 응답에 나타나지 않았다.

파일 단위 오류 검증:

- 첨부 후 삭제·존재하지 않는 경로: 해당 파일 오류 표시, 모델 요청을 보내지 않음.
- 권한 없음: 모의 권한 오류로 파일 단위 처리 확인.
- 파일 잠김: Windows `CreateFileW`의 공유 모드 0으로 실제 파일을 잠근 뒤 읽기 실패 확인. 같은 요청의 정상 PDF는 계속 추출됨.
- 지원하지 않는 확장자, 0 byte, 20 MB 초과, 손상된 PPTX, 암호화 PDF, 텍스트 없는 PDF: 명확한 파일별 오류, 정상 파일 처리 유지.
- 큰 텍스트: 질문 관련 CODE가 파일 끝에 있어도 해당 청크 선택. 생략 표시와 본문 한도 확인.
- 대화 저장·복원: 원본을 삭제한 뒤에도 저장된 본문으로 후속 질문 context 구성 확인.

최종 코드 상태에서 관련 회귀 검사 **86건 통과** 및 기존 `_check_composer_drop` 통과. 최종 TXT 파일 선택 → Iris Agent 응답도 한 번 더 실행해 `TXT-1234`를 확인했다. 메인·IDE UI 렌더링 이미지를 생성해 파일 아이콘과 `test.pptx` 칩, 경로·본문 비노출을 확인했다.

## 로그·증거·재현

기본 로그: `~/.iris-light/logs/attachments.log` (2 MB 회전, 백업 2개). `IRIS_ATTACHMENT_LOG_DIR`로 변경할 수 있다.

단계: `selection` → `composer_send` → `user_turn` → `extract`/`folder` → `agent_context` → `request` → `response`.

로그에는 경로·파일명·MIME·원본 크기·첨부 ID·본문 길이·해시·생략 여부·오류와 HTTP payload 키·메시지별 본문 길이를 남긴다. 실제 사용자 파일 본문이나 인증 키는 기본 로그에 기록하지 않는다. 검증 fixture의 본문은 아래 JSON 요청 증거로 직접 확인할 수 있다.

- [실제 Iris Agent 14건 응답](../.iris_light_test_tmp/attachment-live/hermes-results.json)
- [PPTX 실제 모델 요청 messages](../.iris_light_test_tmp/attachment-live/hermes-main-pptx-picker-messages.json)
- [단계별 실행 로그](../.iris_light_test_tmp/attachment-live/attachments.log)
- [메인 첨부 UI](../.iris_light_test_tmp/attachments/main-attachment.png)
- [IDE 첨부 UI](../.iris_light_test_tmp/attachments/ide-attachment.png)

검증 산출물은 `.iris_light_test_tmp` 아래 생성되며 Git에 포함되지 않는다. 아래 명령으로 재생성할 수 있다.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.venv/Scripts/python.exe -m unittest tests.test_attachment_pipeline tests.test_chat_conversations tests.test_chat_rendering_pipeline tests.test_user_turn_dispatcher tests.test_hermes_auth tests.test_hermes_ollama_options_guard -q
.venv/Scripts/python.exe -m iris.ui.chat._check_composer_drop
.venv/Scripts/python.exe -m scripts.check_attachment_live --backend hermes
# 특정 조합만 재검증
.venv/Scripts/python.exe -m scripts.check_attachment_live --mode main --format txt --method picker
```

## 수정 파일·함수

| 파일 | 주요 함수/변경 |
|---|---|
| `iris/ui/chat/chat_panel.py` | `_on_composer_drop_paths`, `_emit_send`: 실제 경로 유지, 모든 첨부 전달, 단계 로그 |
| `iris/runtime/user_turn_dispatcher.py` | `submit`: 첨부 전달 단계 로그 |
| `iris/runtime/attachment_context.py` (신규) | `Attachment`, `PreparedAttachments`, `prepare_attachments`, `_read`, `_parts`, `_office_parts`, `_ocr_image`, `_relevant_chunks`, `inference_messages`, `trace`, `trace_payload` |
| `iris/ui/workers/attachment_worker.py` (신규) | `AttachmentWorker.run`, `request_cancel`: 비동기 추출·취소·예외 처리 |
| `iris/ui/window/main_window.py` | `_execute_user_turn`, `_continue_user_turn`, `_on_attachment_failed`, `_format_user_turn_content`, `_record_history`, `_chat_messages_with_project_context`, `_on_chat_finished` |
| `iris/runtime/chat_session.py` | `record`: 화면 텍스트와 모델 본문 분리 저장 |
| `iris/storage/conversations.py` | `ensure_chat_schema`, `append_message`, `list_messages`, `history_dicts`, `ChatMessage`: `model_content` 저장·복원·마이그레이션 |
| `iris/infrastructure/hermes_client.py` | `stream_chat`: 최종 HTTP 요청 진단 로그 |
| `iris/infrastructure/ollama_client.py` | `stream_chat`: 최종 HTTP 요청 진단 로그 |
| `iris/infrastructure/openai_compat_client.py` | `stream_chat`: 최종 HTTP 요청 진단 로그 |
| `iris/ui/chat/_check_composer_drop.py` | 기존 체크를 새 전송 계약으로 수정 |
| `tests/test_attachment_pipeline.py` (신규) | 추출·오류·파일 잠금·청크·저장·Qt·운영 전송·HTTP payload 검사 |
| `scripts/check_attachment_live.py` (신규) | 실제 Iris Agent 응답 검증·fixture 요청/결과 저장 |
| `scripts/probe_attachment_runtime.py` (신규) | 읽기 전용 로컬 추론 상태 및 실제 이미지 OCR 오류 확인 |

실제 Iris Agent gateway 내부의 downstream 모델 HTTP 요청을 별도로 계측한 것은 아니다. IRIS의 최종 요청 본문과 gateway의 실제 CODE 응답으로 첨부 데이터가 추론에 사용된 것을 확인했다. Ollama·OpenAI 호환 직행 경로에는 동일한 `messages[].content`를 연결했으나, 이번 14건 실제 모델 응답 검증은 Iris Agent 경로에서 수행했다.
