# Wave 1.7 FFC 실행 추적표

## 00 공통 기준선

- 시작 HEAD `434081fd161f3b011d1897cc5791ccf7100de9c6`, clean worktree. FRC 추적표, FRCV 독립 검증·Wave 2 진입 판정, Wave 2 브리프의 결과는 이전 증거로 취급했다.
- 앱 Python 3.13.7. 활성 `iris-agent.slot-272facc0f5fd4b6f`, 이전 `iris-agent.slot-e38f3ea761714c36`. 검증된 활성 슬롯에서 Python 3.14.7, Core `0.1.2+iris.a382af23`, MCP SDK 2.3.0을 읽었다. 슬롯과 vendor의 `SOURCE_MANIFEST.json`, `uv.lock`, `run_agent.py` SHA-256이 각각 일치했다. Core vendor 및 패키징 변경은 없다.
- 제품 Core 설정의 기본 모델은 `gemma4:e2b`, 요청 `ollama_num_ctx`는 64,000이었다. 로컬 목록에서 이 태그는 없었고 `gpt-oss:20b`, `gemma4:12b` 등은 설치돼 있었다. 모델 실측은 앱을 격리한 테스트 프로필에서 진행했다. 스키마/설정 변경에 외부 API 키를 사용하지 않았다.

## 01 제품 설정 복구

| 항목 | 원인·수정 및 호출자 | 재현과 증거 | 판정 |
| --- | --- | --- | --- |
| FFC-01A 모델 선택 | `resolve_initial_model`이 미설치 선택을 목록 모델로 바꿨다. `iris_agent_errors.py`, `chat_panel.py`, `main_window.py`에서 선택을 유지하고 미설치·연결 실패를 표시한다. Picker → 앱 DB → `resolve_iris_agent_inference` → `IrisAgentChatWorker` → `Engine` → `Sidecar` 경로에서 Ollama `/api/show` 404/연결 오류를 구분한다. `ollama_workers.py`의 직행 Ollama 404도 다른 모델 재요청을 중단한다. | 최초 간단 assert FAIL. `python -m scripts.validate_wave17 gui-chat --recover-model --out .tmp/ffc-01/gui-recovery-404`에서 미설치 상태·전송 404·명시적 선택 DB 저장·실제 정상 채팅·대화 복원·창 종료 PASS. 이전 시도에서 Core의 404 재시도 후 generic 오류를 관찰했다. 별도 연결 복구/8,192 실측은 아래 추가 결과에 기록한다. | L2 PASS, 미설치 복구 L4/L5 PASS |
| FFC-01B 실행 경계 | `agent.disabled_toolsets`는 Core 도구 세트 구성에 사용된다. 제품 Sidecar는 `engine_tool_bindings`를 쓰고 원본 `registry.dispatch`를 차단한다. Native 파일 범위·쉘 승인 및 MCP 호스트 승인은 기존 실행 정책에 있다. 설정 migration을 적용할 필요가 없었다. | `python -m iris.infrastructure._check_native_tool_hermes_disabled`, `_check_native_tool_binding` PASS. 실제 Owned Python에서 `terminal`, `read_file`, `memory` 원본 registry 호출 3/3 차단 (`.tmp/ffc-01/registry-owned/guard.txt`). 격리 `disabled_toolsets: [terminal, file, browser, memory]`에서도 Desktop Native 검색→읽기 및 MCP 승인→응답 grounding PASS (`.tmp/ffc-01/gui-tools-grounding/gui-chat.json`). | L2/L3 PASS, Native/MCP 각각 L4/L5 PASS |
| FFC-01C Context·capability | `ollama_client.py`, `_sidecar_main.py`, `tool_surface.py`에서 advertised·loaded·provider 요청 옵션을 분리했다. 오래된 일반 대화 쌍부터 요청 단위로 줄이며 현재 요청과 현재 도구 결과는 유지한다. 사용자 명시 창을 모델 한도로 제한하고, 스키마 바이트와 시스템·히스토리·첨부·기억·결과·출력·추론 토큰 추정을 분리한다. 도구 미지원 모델은 스키마와 실제 실행 양쪽에서 차단한다. | `python -m unittest tests.test_wave17_adaptive_context -q`, `python -m iris.engine._check_tool_surface` PASS. 실제 Desktop에서 advertised 131,072, 요청 `options.num_ctx=8192` 및 `64000`, 스트리밍 및 provider usage를 관찰했다. 동일 입력 대조에서 실제 loaded는 두 요청 모두 4,096이었다. | L2 PASS. Desktop 응답 L4/L5 PASS. 런타임 창 지정과 Provider별 vision·streaming 거절의 실측은 PARTIAL |
| FFC-01D 제품 작업 묶음 | `scripts/validate_wave17.py`의 격리 GUI fixture에서 실제 Native 경로와 Owned MCP SDK를 연결했다. 첫 일반 첨부 실험은 사전 추출 텍스트로 답할 수 있어 Native 실행을 검증할 수 없었다. 후속 실험은 host `TOOL_RESULT`와 응답의 실제 표식을 사용했다. 명시 shell 요청은 `terminal`을, 명시 로컬 파일은 Native 읽기를 먼저 제공한다. | 일반 채팅, 검색→읽기, 승인 MCP, 승인 Shell, Native+MCP mixed 각각 성공. 혼합 시도가 출력 한도로 실패했을 때 제품 안내에서 관련 없는 세부 지침을 줄였다. 최종 mixed 요청 추정 2,481→3,198토큰, 실제 마지막 prompt 2,871토큰, 관측 창 4,096. | 시나리오별 L4/L5 PASS. 반복 안정성은 05 인수인계 |

## 02 Native Memory와 Wiki 분리

| 항목 | 원인·수정 및 호출자 | 재현과 증거 | 판정 |
| --- | --- | --- | --- |
| FFC-02A 저장·소유권 | Core `tools/memory_tool[_store].py`의 사용자·메모리 파일, `agent/memory_manager*`의 provider hook, `agent/memory_context.py`의 데이터 경계, `tools/session_search_tool.py`와 제품 `chat.search_past`를 확인했다. Core는 `skip_memory=True`다. `iris/storage/memory.py`는 동일 앱 SQLite에 별도 `native_memory` 테이블, 주체별 opt-in, 사용자·프로젝트·세션 범위, host 출처, 중복 인덱스, 수정 전 revision 비교, 삭제 시 본문 비움 및 tombstone을 둔다. | `python -m unittest tests.test_wave17_memory -q`. 모듈 부재로 FAIL을 먼저 재현했다. 현재 주체·범위 차단, 중복, 낡은 revision, 재시작, 삭제, 비활성, 비밀 거부 PASS. | L2 PASS |
| FFC-02B 정책·UI·회수 | `speak_capability.py` → `control_bindings.py` → Native memory 액션으로 연결했다. Desktop의 host 주체와 로컬 Ollama 요청에서 기억을 사용할 수 있다. 변경마다 사용자 승인과 현재 설정·revision을 검증한다. `IrisAgentChatWorker`가 매 요청 scoped 기억을 검색해 크기 제한된 사용자 역할 데이터로 전달한다. `memory_box.py`와 설정에서 활성화, 열람·수정·개별 삭제를 제공한다. | 통합 액션에서 저장 대신 수정, 독립 액션에서 `kind`/`type` 혼동을 재현했다. 선택적 `type` 기본값을 `fact`로 정한 세 번째 시도에서 저장→새 대화 회수→수정→설정 열람→삭제→미회수 PASS. 실제 제품 승인 경로에 fixture 한정 승인 콜백을 사용했다. | L2/L4/L5 PASS |
| FFC-02C Wiki·원본 | 실제 프로필에 Wiki `profile/traits.md`와 Core `MEMORY.md`·`USER.md`가 있었다. 파일은 보존하고 Wiki traits 자동 프롬프트 주입을 제거했다. 검색된 Wiki는 사용자 역할의 비신뢰 참고 자료로 전달한다. 별도 저장소와 기본 비활성 설정을 사용한다. | Wiki/PDF 레퍼런스·기억·Context·turn pytest 54 passed, 7 subtests passed. PDF/OCR 및 실제 Qt 첨부 `python -m unittest tests.test_attachment_pipeline -q` 21 PASS. Windows 파일 권한과 loopback 격리에서 처음 실패한 Native MCP/attachment store는 허용 환경에서 25 PASS, 5 subtests PASS. Wiki 참조 사용자 역할 및 레거시 특성 자동 주입 제외 계약 2 PASS. 실제 기억 변경 전후 Wiki fixture SHA-256 일치. | L2/L5 PASS. 선택적 migration은 원본 목록 확인 단계 |

## 03 Hermes Functional Absorption

| 항목 | 원인·수정 및 호출자 | 재현과 증거 | 판정 |
| --- | --- | --- | --- |
| FFC-03A 도메인 | `TurnTodoStore`+`HostEvidenceLedger`, `ClarifyWaitStore`+`ResumeTicket`, `DelegateSessionRegistry` | `_check_turn_todo_*`, `_check_clarify_wait`, `_check_delegate_session` PASS | L2 PASS |
| FFC-03B Speak 흡수 | `todo_list`/`clarify`/`delegate_task`/`session_search`/`skill_manage` + Unit5 residual → Control; eager `session_search`; STRIP=`memory`만 | `_check_absorbed_tool_wire` **home_n=131**, residual/todo/clarify/delegate manage host PASS | L2/L3 PASS |
| FFC-03C 정직 잔여 | `execute_code`→terminal INTERNAL; cron/connections/computer/image/tts status·dispatcher; raw_desktop unsupported; 시크릿 비노출 | `_check_ffc03_residual_absorb` strip=`['memory']` | L2 PASS. Provider 실호출·실모델 L4는 04 인수인계 |

상세: [wave17-ffc03-functional-absorption-2026-11-27.md](wave17-ffc03-functional-absorption-2026-11-27.md). 04 인수인계: [wave17-ffc04-handoff-from-ffc03-2026-11-27.md](wave17-ffc04-handoff-from-ffc03-2026-11-27.md).

## 04 Gateway 및 MCP Closure

| 항목 | 원인·수정 및 호출자 | 재현과 증거 | 판정 |
| --- | --- | --- | --- |
| FFC-04A signed webhook | `/v1/agent/connectors/*`가 없어 실제 loopback 등록이 404였다. `GatewayStore`에 connector, replay/event, 외부 thread→session mapping을 추가했다. `ControlSurface`는 32 KiB 제한의 webhook만 Bearer 이전에 분기하고 `NativeGateway.webhook`이 canonical JSON, HMAC-SHA256, ±300초 timestamp, nonce/event 중복, 60/min, 허용 channel을 검증한 뒤 기존 `_start`를 사용한다. secret 원문은 저장하지 않고 SHA-256 파생 HMAC key만 저장한다. | 첫 `_check_gateway_webhook_connector`는 404로 FAIL. 구현 후 정상 run/result token, 위조 401, 만료 401, 중복 409, channel 403, disconnect/reconnect, 같은 외부 thread session 재사용, revoke 뒤 token 401 PASS. 인증 실패는 `_start` 전에 끝난다. | L2/L3 PASS. 외부 공개 없음 |
| FFC-04B connector lifecycle | Control Bearer만 등록·disconnect·reconnect·revoke 가능하다. 등록 시 connector principal의 `read,cancel` scoped token을 발급하며 run/Control 승인 권한을 주지 않는다. 결과 전달은 기존 소유권 제한 `/events` pull 계약이다. revoke는 connector와 결과 token을 함께 폐기한다. 독립 Agent Loop/registry는 추가하지 않았다. | 실제 loopback fixture에서 connector event→Owned Gateway run→final events 왕복. Control token은 connector principal의 run을 404로 보며 connector token은 Control 경로에 쓸 수 없다. | L2/L3 PASS. 선택 플랫폼 push adapter·계정은 UNVERIFIED |
| FFC-04C MCP multi-server | 기존 fresh Owned SDK subprocess, STDIO/Streamable HTTP/SSE, tools/resources/prompts를 유지했다. 동시 `tools/call` 두 건이 같은 서버에서 겹치는 실패를 실제 overlap marker로 재현했다. `native_manager.py`에 config path+server별 host lock을 두고 lock 획득 후 config/schema/cancel을 다시 읽는다. read/resource/prompt와 서로 다른 서버는 병렬성을 유지한다. | `_check_multiserver_reconnect`: 동일 이름 도구의 namespace 고유성, 같은 서버 직렬화, 서로 다른 서버 고유 결과, 첫 프로세스 강제 종료 뒤 명시적 다음 discover 복구, timeout `execution_uncertain` 및 0/1회 실행, Desktop registry 거절 시 call 0회 PASS. `_check_schema_refuse_after_approval` 유지. | L2/L3 PASS |
| FFC-04D 실제 통합 | 기존 `NativeGateway`→Engine→`NativeMCPManager.invoke_binding`→Control 승인 경계를 그대로 사용했다. Scoped token은 승인하지 못하고 Control Bearer만 승인한다. Gateway 비활성 Desktop은 별도 경로를 유지한다. | `python -m scripts.validate_wave17 gateway-mcp --out .tmp/ffc-04/gateway-mcp`: 실제 모델+MCP, approval events, grounded final, restart session/run/search, 다른 principal 거절 PASS. 파일 직접 실행 1회는 repo import 경로 부재로 실패 후 모듈 실행으로 보정. `python -m scripts.validate_wave17 gui-chat --out .tmp/ffc-04/gui-mcp --product-tools --mixed-only --ollama-window 8192`: Gateway HTTP disabled, local read+MCP grounding, fixture 승인, window close PASS. | Gateway L4 PASS, Desktop L4/L5 PASS. 수동 사람 click은 UNVERIFIED |

## 실측과 재현

- 소스 지문 `2573a04edd1b1490476c0b7de75c8bc1a30e6d2d2d82b45d2ab511fd5e9cec48`. 24개 변경 소스 및 테스트의 개별 SHA-256은 `.tmp/ffc-evidence/source.json`에 있다. 마지막 관련 unittest 69 PASS, 별도 Wiki 역할 검사 2 PASS, `compileall` 및 `git diff --check` PASS.
- FFC-01A 연결 복구는 `python -m scripts.validate_wave17 gui-chat --recover-model --ollama-window 8192 --out .tmp/ffc-01/gui-window-8192-bounded`. 두 차례 보정 후 미설치 404, 연결 실패 시 선택 유지, 명시적 설치 모델 선택 DB 저장, 설치 모델 스트리밍 응답 및 창 종료 PASS.
- FFC-01D `--product-tools`와 `--mixed-only`는 총 7회 시도했다. 검색→읽기는 `.tmp/ffc-01/gui-tools-grounding/gui-chat.json`, 승인 쉘은 `.tmp/ffc-01/gui-tools-priority/gui-chat.json`, 최종 혼합 성공은 `python -m scripts.validate_wave17 gui-chat --mixed-only --out .tmp/ffc-01/gui-mixed-compact-policy`에 있다. 혼합 호스트 로그에서 `local.read_file` 다음 MCP 실행이 각각 성공했고, 답변에 양쪽 실제 표식이 들어갔다. 도구 시작 뒤 실패한 턴을 모델 장애 조치로 재실행하는 경우도 회귀로 재현해 차단했다.
- FFC-02 `python -m scripts.validate_wave17 gui-chat --product-memory --out .tmp/ffc-02/gui-memory-fact`의 `gui-chat.json`과 `profile/engine.log`에 세 번째 시도 결과가 있다. Core Wiki 파일의 실제 사용자 내용과 API 비밀 값은 증거에서 제외했다.
- FFC-04 관련 pytest는 Gateway/Control 6 PASS·live 1 skip, MCP 11 PASS, Hermes Gateway 진단 19 PASS다. 신규 자검 3건(webhook connector, multi-server/reconnect, schema refuse)과 gateway-legacy-isolated도 PASS다. Owned Python 3.14.7의 MCP SDK 2.3.0에서 `ClientSession.call_tool`, `read_resource`, `get_prompt` 실제 signature를 읽었다. `compileall`, `git diff --check`, product-ready-no-gateway, product-no-gateway-spawn, native-tool-hermes-disabled가 통과했다.
- FFC-04 소스 SHA-256: `gateway.py` `9fb3f981…`, `native_gateway.py` `64350ee8…`, `control_surface.py` `6143a38f…`, `native_manager.py` `7d55a7ec…`, webhook 자검 `0cda6c1a…`, MCP 자검 `cb803e7d…`. 전체 inventory 재실행은 baseline의 BOM 포함 Python 파일을 `ast.parse`하는 기존 하네스 결함으로 source.json 작성 뒤 중단했으며 04 개별 지문과 기능 검증에는 영향이 없다.
- FFC-01C 동일 모델·입력으로 `/v1/chat/completions`에서 `options.num_ctx=8192`와 `64000`을 순서대로 요청했다. 실제 `/api/ps`는 모두 4,096, 종료 사유는 모두 `stop`이었다. 관측 지연 11.762초와 0.295초는 두 번째 요청의 캐시 히트 때문에 창 크기의 성능 차이로 해석할 수 없다. 광고 131,072는 모델 한도다. 요청 값은 런타임 창의 보장이 아니다. `.tmp/ffc-evidence/ollama-context-contrast.json` · [Ollama OpenAI 호환 API의 컨텍스트 설정](https://docs.ollama.com/api/openai-compatibility#setting-the-local-context-size)

## 실행 증거와 인수인계

- 실행 명령은 앱 venv의 Python을 사용했다. pytest는 로컬 시스템 Python에 설치돼 있어 `PYTHONPATH`로 앱 venv 패키지를 사용했다. 루프백·실제 Qt 테스트는 권한이 필요한 경우 격리 프로필/fixture로 재실행했다. 시스템 서비스 재시작이나 모델 다운로드는 없었다.
- L2 Native·MCP 검사와 L4/L5 모델 결과를 별도로 기록한다. 셸 및 mixed 판정은 실제 host 실행 성공과 응답 근거를 모두 요구한다.
- 03 인수인계에서는 `native_memory` ID·주체·스코프·출처 계약과 `chat.search_past`의 별도 권한 경계를 사용한다. 05에는 같은 턴 혼합 성공과 이전 출력 한도 실패를 함께 넘긴다.
- 04→05 인수인계: [wave17-ffc05-handoff-from-ffc04-2026-11-27.md](wave17-ffc05-handoff-from-ffc04-2026-11-27.md).

## 05 Agent 및 Document Reliability

| 항목 | 원인·수정 및 호출자 | 재현과 증거 | 판정 |
| --- | --- | --- | --- |
| FFC-05A Agent recovery | `iris/system/agent_recovery.py`에 `RecoveryClass` 진단 표, `should_auto_retry`(uncertain 부작용 금지), `recover_path_arg`(명시 스코프만). MCP 루프 미개입. | `_check_ffc05_agent_recovery` PASS. `_check_multiserver_reconnect` 유지. 실모델 10회 Native/MCP/mixed는 미실행. | L2 PASS. 10회 L4 UNVERIFIED |
| FFC-05B Canonicalize + OCR cancel | `AttachmentStore.canonicalize_attachment_ref` 유지. `wiki.content_extract` 성공 시 canonical id echo. `_check_ocr_cancel` mid-OCR cancel→`EXTRACTION_CANCELLED`. | `_check_pdf_page_range`, `_check_ocr_cancel` PASS | L2 PASS |
| FFC-05C Extraction cache | Arena base Candidate B. `extraction_cache.ExtractionMemo` per store, TEMP spill. `extract_from_source` pdf\|image만 wrap. vision/error 미적재. store clear/detach/drift invalidate. | `_check_extraction_cache` PASS. page-range / OCR fast / chip enrich PASS | L2 PASS |
| FFC-05D 201p page window | `_ffc05_pdf_fixture` 생성기 + `_check_ffc05_pdf_201p` (page 87/201 marker, unread 미혼입). | L2 PASS. 실모델 L4 UNVERIFIED | L2 PASS, L4 UNVERIFIED |

상세: [wave17-ffc05-agent-document-2026-11-27.md](wave17-ffc05-agent-document-2026-11-27.md). 06 인수인계: [wave17-ffc06-handoff-from-ffc05-2026-11-27.md](wave17-ffc06-handoff-from-ffc05-2026-11-27.md).

## 06 Product Regression

**부분 완료.** 원본 JUnit 실패 36건의 대응 검사, Windows 전체 pytest, FPR-13 계약과 격리 설치 수명주기, 반복 Process 승인 및 종료 취소를 확인했다. 실제 모델 스트리밍과 진행 중인 OCR 종료도 확인했다. 실제 Memory 삭제 및 일부 GUI와 작업 중 종료 시나리오가 남았다.

| 검증 | 결과 | 증거 |
| --- | --- | --- |
| 역사적 실패 | 36개 실패 요소와 19개 고유 ID 대조 | [대응표](wave17-ffc06-product-regression-2026-11-28.md) |
| First-party pytest | 기본 1,292 PASS · 3 SKIP. Windows 플랫폼과 Gateway 모델을 활성화한 최신 재검은 1,296 PASS · 199 subtest PASS · 1 SKIP(qwen-tts) · 0 FAIL · 0 ERROR · 0 abort | `.tmp/ffc-06/pytest-final.xml`, `.tmp/ffc-06/pytest-verified.xml` |
| NIP-12 | 기존 실행 명령 54/54, FPR-13 계약 17/17, launcher 존재와 KEEP 확인 | `.tmp/ffc-06/fpr13-contracts/results.json`, [회귀 기록](wave17-ffc06-product-regression-2026-11-28.md) |
| FPR-13 | 최신 혼합 실행 23 PASS · 1 FAIL · 1 UNVERIFIED. 실패한 L3 실제 셸은 수정 후 집중 PASS, IDE L4는 전용 제품 홈 9/9 PASS | `.tmp/ffc-06/fpr13-release/results.json`, `.tmp/owned-live-shell/required/8814541aaa3c47fca08b27c9fd909792/evidence.json`, `.tmp/ffc-06/product-home-recheck/results.json` |
| Process 및 Qt | Skip 10/10, Run 10/10, 미결정 승인 중 종료 10/10. 대화 전환, 실제 Tesseract 실행 중 종료, 실제 모델 생성 중 정상 종료 확인 | `_check_fpr_product_gui process`, `_check_fpr_product_gui ocr-shutdown`, `.tmp/ffc-06/gui-stream-verified/gui-chat.json` |
| 실제 모델 GUI | Model Picker 미설치·연결 오류·선택 보존, Gateway 없이 중간 청크 12개·최종 응답·대화 복원 | `.tmp/ffc-06/gui-chat-closure/gui-chat.json` |
| 모델 도구 | Memory 저장·회상·목록 PASS, 갱신은 실행 간 편차, 삭제는 확인 실패. 최종 혼합 GUI에서 Native·MCP 호출 PASS, 모델의 하이픈 치환으로 정확 일치 FAIL. Todo/Clarify 및 MCP 다중 재연결은 계약 PASS | `.tmp/ffc-06/gui-memory-recheck/gui-chat.json`, `.tmp/ffc-06/gui-memory-final/gui-chat.json`, `.tmp/ffc-06/gui-mcp-verified/gui-chat.json` |

[FFC-07 인수인계](wave17-ffc07-handoff-from-ffc06-2026-11-28.md)

## 07 Foundation Certification

**PARTIAL.** 최종 코드에서 FPR-13 전 시나리오, L7 도구·Provider·확장 계약, 격리 슬롯 수명주기 및 로컬 패키지 빌드를 확인했다. 실모델 제품 경로의 재현 편차와 별도 클린 Windows 설치를 남겼다. [MASTER 08 인수인계](wave17-ffc08-handoff-from-ffc07-2026-11-28.md)

| Wave 2 요구 | Wave 1.7 기반 계약·현재 실행 증거 | Wave 2 범위와 잔여 위험 |
| --- | --- | --- |
| U07 Agent Performance | 요청·문맥 기반 도구 제한과 검색·설명·호출. 새 Speak 도구를 실모델이 `tool_describe`로 발견하고 host 승인 뒤 호출했다. `.tmp/ffc-07/native-final/foundation-native.json` 및 `agent/logs/agent.log`. | 명시 프로파일, 안전한 읽기 병렬화, 압축·캐시 최적화는 Wave 2. 성능 기준선과 실제 요청별 Ollama 할당 창은 추가 계측이 필요하다. |
| U08 Memory & Skill | 상태·소유권을 분리한 SQLite Memory와 Wiki, 스킬 조회·생성·활성·수정·비활성·보관과 승인. 격리 GUI에서 저장, 새 대화 회상, 갱신, 설정 목록, 삭제, 삭제 후 미회상, Wiki 해시 유지 모두 PASS. `.tmp/ffc-07/extension-fixture.log`, `memory/gui-chat.json`. | 상세 기억 분류와 절차 재사용은 Wave 2. 이전 실행에서 메모리 변경 편차가 있었으며 이번 재검은 한 시도다. |
| U09 Orchestration | Todo 저장/복원 및 host evidence, Clarify 대기/재개, Delegate 상한. 복사 DB와 별도 Todo 파일을 L6에서 복원했고 기존 단위 계약을 유지했다. | 장기 계획·가변 권한 상속·고급 실행 제어는 Wave 2. 실제 모델 Todo/Clarify UI와 Voice 상태 전환은 미검증이다. |
| U10 Provider & MCP | Ollama NDJSON/OpenAI 호환 SSE 오류·스트림 종료 계약, Core의 독립 loopback API 도구 스트리밍과 결과 ID, 실제 MCP 승인·실행·업데이트·비활성·제거, Gateway 재시작 후 세션/검색. `.tmp/ffc-07/provider-owned-verified/result.json`, `mcp/mcp-results.json`, `gateway/gateway-result.json`. | 단일 어댑터 정교화, 추가 Provider 및 확장 프로파일은 Wave 2. 외부 OAuth 및 외부 계정 연결은 별도 증거가 필요하다. |
| U11 Extended Capabilities | Wiki/Browser 실제 Qt, 승인 Process/Shell, IDE 9/9, PDF 페이지 범위 및 캐시·OCR 계약. 201쪽 문서의 87쪽 실제 모델 작업에서 정확한 표식을 회수했다. `.tmp/ffc-07/product-home`, `document-final/result.json`. | Browser/Aloha/Routine/vision 공통화는 Wave 2. GUI Native 검색·Shell 실행의 반복 안정성과 Voice 실측을 추적한다. |

- **07A L7 PASS.** `scripts/_check_foundation_native.py`는 격리된 Speak 등록, 타입 스키마·고위험 승인·취소 확인, 실모델 발견·실행과 요청/도구 호출 ID 상관관계, 제거 뒤 기본 ping을 검증한다. `validate_wave17`의 실제 stdio MCP 수명주기와 기존 Skill 승인 계약도 통과했다. 범용 Speak 검증기의 타입·필수 필드 검사와 액션별 enum/형식 검사를 구분한다.
- **07B Provider 오류 수정 PASS.** 처음 두 loopback 테스트가 HTTP 200 스트림 본문의 오류를 놓쳤다. `ollama_client.py`, `openai_compat_client.py`에서 명시적 오류를 소비자에 전달한 뒤 두 대조군이 통과했다. `tests/test_wave17_foundation_provider.py`는 컨텍스트 한도·도구 플래그·조기 종료도 확인한다.
- **07C L6 PASS.** `_check_foundation_data`가 구형 채팅 SQLite 복사본을 열어 기존 대화/일반 텍스트를 유지했다. 세션·첨부·Memory·Todo·Gateway run/이벤트·비활성 MCP 등록은 업데이트와 복구 후 검증했다. Core 후보 및 롤백을 포함한 gpt-oss:20b 네 번의 실모델 응답과 격리 전 상태는 `.tmp/wave16-lifecycle/run-m8vigc7v/evidence.json`에 있다. 별도 클린 Windows Setup은 **BLOCKED**.
- **07D 레거시 감사 PASS.** 전체 저장소에서 호출자를 찾지 못한 전역 사이드카 탐색/종료 헬퍼 두 개를 제거했다. 제거 전 정적 검사 FAIL, 제거 후 owned 생명주기와 Gateway 미기동 PASS. 진단·설치·복구의 호환 호출은 인수인계에 남겼다. `legacy_migration_approved=false`.
- **07E 문서 회귀 수정 PASS.** 1쪽만 읽은 PDF 응답에 미열람 200쪽 상태가 포함돼 실제 4,096토큰 창에서 모델 답이 빗나갔다. `iris/engine/runtime.py`와 `tests/test_wave17_turn_context.py`에서 모델에 전달하는 응답에만 미열람 건수를 집계했다. 원본 추출 데이터와 직접 호출의 페이지별 상태를 유지한다. 실제 도구 결과 크기 13,740→668자, 87쪽 표식 정확 일치. `.tmp/ffc-07/document-verified`, `document-retry`, `document-final`.
- **07F L1–L6 및 빌드.** 최종 Windows pytest 1,299 PASS·199 subtest PASS·1 SKIP·0 FAIL/ERROR. FPR-13은 두 실행을 합쳐 고유 시나리오 25/25 PASS. Launcher와 Setup 0.1.18의 로컬 빌드·SHA-256 및 최종 설치 payload를 검증했다. 작업 트리 지문 `5717572f990c61be6cd6add32e537ac1a82b72be468d533dab92a403f04ad9a5`. 증거는 `.tmp/ffc-07/inventory/source.json`, `fpr13-combined.json`, `pytest-final.xml`, `package-source-final.json`, `package-sha256-final.json`.
- **07G GUI PARTIAL.** 최종 도구 GUI에서 MCP, 혼합 및 Shell은 PASS. 별도 Native 폴더 검색이 두 시도에서 두 도구를 호출하지 않아 FAIL. 독립 headless의 검색→읽기와 GUI 혼합의 Native 읽기는 PASS. 최종 GUI 실제 모델 스트리밍 중 창 종료는 PASS. `.tmp/ffc-07/gui-tools-final/gui-chat.json`, `native-file/native-results.json`, `gui-shutdown-final/gui-chat.json`.

## 남은 검증

- Ollama `/v1`에서 런타임 창 변경은 미확인이다. 지원되는 모델 설정 또는 Native API 경로에서 동일한 테스트를 반복해야 한다. 이번 실행은 사용자 태그·모델 설정을 변경하지 않았다. Vision 미지원 및 streaming 거절 처리의 실제 제품 시나리오, 물리적 모델 삭제 및 앱 재시작 후 선택 보존의 GUI 시나리오도 미검증이다. 404, 연결 복구, DB 저장, 평문 스트리밍은 검증했다.
- 과거 액션 스냅샷 차이는 `.tmp/ffc-evidence/legacy-catalog-drift.json`에 있다. FFC-06에서 정적 스냅샷과 현재 실행 레지스트리 183개의 이름, 설명, 위험도, 승인 플래그 일치를 확인했다.
- FFC-04에서 실제 외부 Slack/Teams 등 계정 연결, push delivery adapter, OAuth adapter, 공개 TLS endpoint는 승인·계정 부재로 구현·실측하지 않았다. 현재 OAuth 설정은 `unsupported_auth`로 안전하게 거부된다. GUI MCP 허용은 제한된 fixture 승인 콜백으로 검증했고 실제 사람이 다이얼로그에서 허용/거절한 화면 증거는 남기지 않았다. 기존 Hermes :8642는 자동 시작하지 않았으며 제품 정상 경로는 :8765 loopback 및 Gateway-free Desktop이다.

## 08 Independent Final Validation

**NO-GO.** 독립 검증 보고서는 [wave17-master08-independent-validation-2026-11-28.md](wave17-master08-independent-validation-2026-11-28.md)에 있다.

- 최종 코드 지문 `b15f5ef9050b383e715a15299b820be6c567a9ccee4f29f41d0407a2814c3f9d` (4,140 files). 검증 도구의 CP949 콘솔 출력만 한 줄 수정했으며 최초 실패와 수정 후 PASS를 모두 보존했다.
- 전체 pytest 1,299 PASS·199 subtests PASS·optional 1 SKIP. FPR-13 core 24 PASS·1 분리 항목은 전용 제품 홈에서 IDE 9/9 PASS. 격리 lifecycle PASS, 클린 Windows BLOCKED.
- Headless 실제 모델은 Native/MCP/mixed 각 10/10, grounding 100%, 권한 위반 0. Gateway/MCP, Memory 7/7, Process GUI 10/10, 스트리밍 종료, L7 Native, 201p PDF 87쪽은 PASS.
- 제품 GUI 도구 묶음은 두 실행 모두 전체 FAIL. 최초는 Native 무호출 및 Shell 미실행 가짜 성공, 재시도는 Native 검색 생략 및 mixed grounding 실패다. 이 기반 P1과 Todo/Clarify/Delegate·OCR/Voice의 실제 제품 공백 때문에 Wave 2 진입을 승인하지 않는다.
