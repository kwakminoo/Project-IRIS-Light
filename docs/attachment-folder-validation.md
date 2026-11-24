# 첨부파일·폴더 처리 확장 검증

검증일: 2026-10-02. 기존 작업 트리에 있던 첨부 추출/전달 변경을 보존하고 폴더 검색과 채팅별 접근 범위를 확장했다.

## 지원 형식

- TXT, MD/Markdown, JSON, CSV/TSV.
- Python, JavaScript/TypeScript, Java, HTML/CSS, C/C++, C#, Go, Rust, Kotlin 등 코드 파일.
- YAML, TOML, INI, CFG, CONF, XML, SQL, 셸 스크립트 및 Dockerfile/Makefile 등 텍스트 설정 파일.
- PDF: 페이지별 텍스트와 페이지 번호.
- DOCX: 문단, 표 행/셀, 머리글/바닥글.
- PPTX: presentation relationships의 실제 슬라이드 순서와 슬라이드 번호.
- XLSX: 시트 이름, 셀 주소/값, shared strings, inline strings, 저장된 수식/계산값.
- CSV/TSV는 열과 행 배열로 전달하며 JSON은 원문 구조를 유지한다.
- PNG/JPEG/WebP/GIF/BMP/TIFF: 기존 Tesseract OCR 경로. 현재 환경에는 Tesseract 실행 파일이 없어 실제 OCR은 사용할 수 없으며 오류 안내를 확인했다. 시각적 이해/이미지 생성과는 별개다.

## 공통 처리 구조

파일 선택, 새 Add Folder 메뉴, Windows 로컬 URL 드롭 → 동일한 composer attachment strip → `UserTurn.attachments` → `AttachmentWorker` → `prepare_attachments` → 세션의 `AttachmentStore` → 구조/선택된 본문 → `model_content` → 기존 Iris Agent/Ollama/OpenAI 호환 메시지 파이프라인.

추출은 Qt GUI 스레드 밖에서 실행한다. UI에는 이름만 표시하며 추출 본문은 모델용 메시지로 분리한다. 모델용 첨부 메타데이터 JSON에서 절대 경로와 폴더 루트를 제거한다. 본문은 줄바꿈을 유지한 텍스트 블록으로 전달하고 폴더 인덱스를 본문보다 먼저 배치한다. 첨부 데이터 뒤에도 질문을 표시한다. 저장된 모델용 본문으로 과거 대화 내용을 볼 수 있지만 로컬 경로 접근 권한은 DB에서 복원하지 않는다.

## 폴더와 검색

폴더 등록 시 파일 본문을 추출하지 않고 목록/메타데이터만 저장한다. 메타데이터에는 이름, 절대 경로, 상대 경로, 확장자, MIME, 크기, 수정 시각, 첨부 ID, 폴더 루트, 추출 여부가 포함된다.

질문별로 상대 경로/파일명 일치와 텍스트·코드의 스트리밍 문자열 검색을 결합한다. 경로/파일명 일치에 본문 출현 빈도보다 높은 가중치를 부여하며 명시한 상대 경로는 해당 파일들만 선택한다. 확장자로 필터링할 수 있고 결과에는 일치한 줄 번호와 제한된 발췌가 들어간다. 한글 조사와 영문 식별자를 분리하며 로그인 질문에는 login/signin/authenticate 검색어를 추가한다. 코드 질문에는 소스를 우선하고, 구현 질문에는 배포 복사본과 검증 스크립트보다 실제 구현을 우선한다. 폴더마다 최대 6개 파일을 선택하고 검색 일치가 없으면 README를 우선해 최대 3개 파일을 읽는다. 일반 문서의 폴더 검색은 파일명 기반이며 선택된 문서 내부에서는 청크를 검색한다. 가장 관련된 소스는 파일명을 명시한 본문 블록으로 질문 가까이에 배치한다.

기본 제외: `.git`, `node_modules`, `dist`, `build`, `out`, `target`, `.venv`, `.venv-*`, `venv`, `__pycache__`, `coverage`, `.next`, `.cache`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`와 IRIS 테스트 출력 디렉터리. `AttachmentStore(exclude_patterns=...)`로 추가 glob 패턴을 지정할 수 있다. 별도의 설정 UI는 추가하지 않았다.

## 청크와 한도

텍스트는 인코딩 검증 후 3,000자씩 스트리밍한다. 작은 문단/표 행은 청크에 함께 묶으며 PDF/슬라이드/시트의 원본 위치 라벨을 유지한다. 추출 청크를 질문의 문자열 일치로 점수화하고 bounded heap으로 필요한 청크만 보관한다. 뒤쪽 페이지/청크도 검사한다. 컨텍스트가 작은 경우 일치 지점 주변을 발췌한다.

- 파일 최대 20 MB, Office 압축 해제 총량 최대 40 MB.
- PDF 최대 200페이지.
- 세션 첨부 루트 최대 50개, 폴더 탐색 항목 최대 2,000개.
- 텍스트 검색은 호출당 최대 60 MB, 검색 결과 최대 50개.
- 한 턴의 추출 본문/폴더 목록 합계 최대 24,000자. 메타데이터/JSON 포장과 과거 대화는 이 본문 한도에 포함되지 않는다.
- 폴더 목록은 최대 4,000자이며 목록/본문 생략과 인덱스 한도는 `truncated`로 표시한다.

## 내부 Tool API와 보안

`AttachmentStore`가 제공하는 내부 API:

1. `list_attached_files(attachment_id=None)`
2. `read_attached_file(attachment_id, relative_path, query=..., budget=...)`
3. `search_attached_files(query, attachment_id=..., extension=..., limit=...)`
4. `list_attached_directory(attachment_id, relative_path="")`
5. `read_file_chunk(attachment_id, relative_path, chunk_index=0)`

현재 앱이 이 API를 호출해 질문별 컨텍스트를 준비한다. Iris Agent 서버에 모델이 직접 호출하는 native tool로 등록한 것은 아니다.

읽기는 현재 세션에서 사용자가 직접 첨부한 루트의 인덱스 항목에 한정한다. `../`, 절대 경로, 드라이브 경로, Windows ADS를 거부하고 실제 resolved path의 범위를 재검증한다. 파일/부모 디렉터리의 심볼릭 링크와 정션도 거부한다. 새 채팅, 채팅 전환, 기록 초기화 때 새 store로 교체하며 이전 worker가 보유한 store도 새 채팅과 분리된다.

누락/삭제, 접근 권한/잠금, 지원하지 않는 형식, 손상된 Office 파일, 암호화 PDF, 스캔 PDF, 크기 한도, 0 byte, 바이너리 텍스트 오류는 파일별 안내로 처리한다. 한 파일 실패가 다른 첨부의 처리를 중단하지 않는다.

## 검증 결과

자동 UI 검증은 실제 ChatPanel과 IDE companion mount 및 MainWindow 전송 메서드를 사용하며, 시작 화면·TTS·외부 MCP 부수 효과만 harness에서 대체한다. 실행 중인 데스크톱 창에서 수행한 수동 클릭 검증은 아니다.

회귀 테스트 **53개 통과**, `git diff --check` 통과. 테스트 명령:

```powershell
.venv/Scripts/python.exe -m unittest tests.test_attachment_pipeline tests.test_attachment_store tests.test_user_turn_dispatcher tests.test_chat_conversations -q
```

실제 추론은 실행 중인 Iris Agent gateway와 로컬 `gemma4:e2b`를 사용했다. UI에서 추출한 내용을 실제 HTTP 요청으로 보낸 뒤 응답의 값/파일명을 확인했다.

| 실제 모델 테스트 | 메인 채팅 경로 | IDE 채팅 경로 | 확인 내용 |
|---|---|---|---|
| TXT | 통과 | 통과 | 선택/드롭 모두 `TXT-1234` |
| PDF | 통과 | 통과 | 선택/드롭 모두 `PDF-5678` |
| PPTX | 통과 | 통과 | 선택/드롭 모두 `PPT-9999` |
| 여러 파일 | 통과 | 통과 | `a.txt → AAA-111`, `b.txt → BBB-222` |
| 폴더 구조 | 통과 | 통과 | README, src/config.py, docs/guide.md 실제 목록 |
| 폴더 README | 통과 | 통과 | 후속 질문에서 `FOLDER-777` |
| 폴더 설정 | 통과 | 통과 | 후속 질문에서 `IRIS_FOLDER_TEST` |
| 파일 + 폴더 | 통과 | 통과 | `AAA-111`과 `IRIS_FOLDER_TEST` 함께 반환 |
| 실제 프로젝트 MCP 검색 | 통과 | 통과 | 파일명 힌트 없이 `iris/mcp/iris_control_stdio.py`와 stdio/JSON-RPC → Iris HTTP 제어 API 브리지 역할 설명 |

DOCX/XLSX, JSON/CSV/코드/설정 파일의 본문 추출과 메타데이터는 실제 fixture 파일을 사용한 자동 테스트로 확인했다. 이미지의 실제 OCR 성공은 확인하지 못했으며 Tesseract 부재 오류를 확인했다. 101페이지 PDF의 마지막 페이지 코드 선택, 긴 코드 끝의 식별자 검색, 경로 이탈/Windows ADS 차단, 실제 Windows 정션 교체 후 외부 파일 접근 차단, Windows 독점 파일 잠금, 첨부 한도, 새 채팅 격리도 테스트했다.

초기 실모델 검증에서 혼합 첨부/IDE 폴더 질문을 무시하거나 프로젝트 설계 문서·검증 스크립트에 치우치는 실패가 있었다. 질문 재표시, 읽기 쉬운 본문, 소스 식별 표시, 구현 소스 우선순위와 관련성에 따른 배치 수정 후 재검증했다. 최종 고유 UI/실모델 사례는 **26개 통과**이며 초기 실패 로그도 보존했다. 이는 모델의 모든 문장을 사실 검증했다는 의미는 아니다. 현재 `gemma4:e2b`가 MCP 약어를 잘못 풀어 쓰는 오류는 남아 있다. 최종 프로젝트 판정은 실제 구현 파일 인용과 브리지 역할 설명을 기준으로 했다.

증거 파일:

- `.iris_light_test_tmp/attachment-live/hermes-results.json`: TXT/PDF/PPTX/폴더, 선택·드롭, 두 UI 경로 14개.
- `.iris_light_test_tmp/attachment-live/extended-results.json`: 초기 확장 사례와 실패 기록.
- `.iris_light_test_tmp/attachment-live/extended-main-mixed-results.json`: 혼합 첨부 수정 후 재검증.
- `.iris_light_test_tmp/attachment-live/extended-ide-folder-tree-results.json`: IDE 폴더 구조 수정 후 재검증.
- `.iris_light_test_tmp/attachment-live/extended-all-project-search-results.json`: 최종 메인/IDE 프로젝트 검색 결과.
- `.iris_light_test_tmp/attachment-live/final-validation-results.json`: 위 결과를 최종 사례별로 통합한 기록.
- `.iris_light_test_tmp/attachments/main-attachment.png`, `ide-attachment.png`: Qt 컴포넌트 렌더 캡처.

## 변경 파일

- `iris/runtime/attachment_context.py`: 스트리밍/구조별 추출, 청크 선택, 메타데이터, store 공통 진입점.
- `iris/runtime/attachment_store.py`: 폴더 인덱스, 범위 제한 내부 도구, 질문별 파일 선택.
- `iris/runtime/chat_session.py`: 세션 소유 store와 채팅 격리.
- `iris/ui/workers/attachment_worker.py`: 세션 store를 백그라운드 준비 작업에 전달.
- `iris/ui/window/main_window.py`: 첫 첨부와 후속 질문의 동일 파이프라인 연결.
- `iris/ui/chat/chat_panel.py`, `iris/ui/chat/composer_plus_menu.py`: 폴더 선택 메뉴/공통 콜백.
- `tests/test_attachment_pipeline.py`, `tests/test_attachment_store.py`: 형식/UI/폴더/청크/범위/격리/실제 프로젝트 회귀 검증.
- `scripts/check_attachment_extended_live.py`: 여러 파일, 폴더 후속 질문, 혼합 첨부, 프로젝트의 실제 Iris Agent 응답 검증.
- `docs/attachment-folder-validation.md`: 이 검증 보고서.

## 남은 제한

이미지 OCR은 현재 환경에서 사용할 수 없다. 스캔 PDF OCR, DOC/PPT/XLS 같은 구형 Office 형식, 도형·차트·레이아웃의 시각 분석, 임베딩 검색, 함수 호출 그래프 분석은 제공하지 않는다. 프로젝트 탐색은 제한된 인덱스와 문자열 검색이므로 대형 폴더는 일부 결과가 생략된다. 현재 파일 목록은 첨부 시점 스냅샷이며 이후 새로 생긴 파일은 자동 인덱싱하지 않는다. 채팅을 나갔다 돌아오거나 앱을 재시작한 뒤 로컬 파일 검색을 계속하려면 다시 첨부해야 한다. 기록의 이미 추출된 본문은 남아 있지만 접근 권한은 복원되지 않는다.
