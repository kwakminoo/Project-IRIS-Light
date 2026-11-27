# IRIS Wave 1.7 구현 추적표

기준선은 clean `main`의 `c51d5ba6e88157ad7d9c9fb196a49aa8094e4bfe`다. Vendor와 활성 `iris-agent.slot-272facc0f5fd4b6f` 모두 `0.1.2+iris.a382af23`이며 `verify_owned_core_source`가 양쪽의 매니페스트 해시 13개와 패키지 정체성을 검증했다. 이전 슬롯은 `iris-agent.slot-e38f3ea761714c36`이다. `legacy_migration_approved=false`다.

종료 판정은 **IMPLEMENTATION PARTIAL**이다. Native Gateway의 인증된 로컬 Agent API와 MCP 등록·탐색은 동작한다. Gateway 세션 영속화와 MCP 도구의 모델 실행 연결은 남았다.

## Phase

| Phase | 구현 ID | 기준 상태와 변경 | 로컬 증거 | 잔여 |
|---|---|---|---|---|
| NGI-00 | W17-BASE | 실측 기준선과 아래 기능 흡수 매트릭스 | 매니페스트 13/13 양쪽, Owned HELLO 통과 | Wave 1.6의 일부 구간은 실측 재검 필요 |
| NGI-01 | W17-CALLERS | 아래 호환성 매트릭스에 변경 경로 기록 | Sidecar 파이프 및 Qt 디스패치 확인 | 후속 모듈 이동 전 각 호출자 추가 조사 |
| NGI-02 | W17-AUTHORITY | Desktop → Engine/Sidecar → SpeakTools → Native Policy 정본. HTTP 비활성·바인딩 실패에도 네이티브 액션 등록 유지 | `test_wave17_control_surface.py`, `_check_tool_contract`, `_check_speak_surface_shell` | 외부 도구 실행 통합 |
| NGI-03 | W17-TURN | `ExecutionContext` 스냅샷과 Qt 호출 연결, 파이프 대기 중 취소 및 동시 턴 거절 수정 | `tests/test_wave17_turn_context.py`, `_check_execution_context` | 외부 세션 소유권과 재시작 복구, 이벤트 영속화 |
| NGI-04 | W17-GATEWAY-AUDIT | 기존 IRIS 및 Vendor Gateway 경계 조사 | 아래 아키텍처 | Webhook, 연결, 승인 전달의 동등성 검증 |
| NGI-05 | W17-GATEWAY | **PARTIAL**. `native_gateway.py`와 기존 `ControlSurface`에 인증, 실행, 상태, 스트리밍, 취소를 연결 | HTTP 통합 계약 및 실제 Owned Ollama 턴 | 세션 영속화와 권한 분리, 승인 이벤트, 재기동 복구 |
| NGI-06 | W17-MCP | **PARTIAL**. `native_manager.py`, 기존 YAML, 등록 UI와 확장 설치 쓰기 경로 통합 | STDIO·Streamable HTTP·SSE 탐색, 설정 보존, 등록 검증 | OAuth, 장기 연결, 자동 재연결, 앱 리소스 호출자 이전 |
| NGI-07 | W17-BINDINGS | **PARTIAL**. 호스트의 기존 네이티브 바인딩과 fingerprint를 턴 단위로 고정 | `test_tool_bindings_are_snapshotted_for_the_turn` | 외부 Binding, 승인 후 config/schema 재검증, MCP 실행 |
| NGI-08 | W17-DISCLOSURE | 기존 `tool_search`, `tool_describe`, `tool_call`과 Native Dispatcher 유지 | FPR13 도구 계약 | 외부 MCP/확장 progressive disclosure와 실제 멀티툴 증거 |
| NGI-09 | W17-CONNECTORS | Gateway Agent API 일부 동작 | NGI-05 HTTP 테스트 | Webhook 및 메시징/백그라운드 전달 |
| NGI-10 | W17-MEMORY | 기존 정본 확인 | 하단 매트릭스 | 외부 세션 소유권과 기억 정책, 영속화 |
| NGI-11 | W17-EXTENSIONS | MCP 등록 저장 공용화 | GitHub 확장 계약 | 플러그인 Hook 권한 통합 및 라이프사이클 |
| NGI-12 | W17-PLANNING | 기존 후속 질의/진행 상태 확인 | 기준선 감사 | Todo와 Clarify 모델 호출·재개 |
| NGI-13 | W17-DELEGATION | 개별 워커의 `Engine.fork` 확인 | 동시 턴 계약 | 부모/자식 권한·예산·취소 |
| NGI-14 | W17-COMPUTER | 기존 Shell/IDE/Browser/에뮬레이터/Aloha 확인 | 기준선 감사 | 인라인 코드 실행과 컴퓨터 제어 통합 검증 |
| NGI-15 | W17-AUTOMATION | Routine과 Core cron 대응 경로 확인 | 기준선 감사 | 승인 범위, 예약 에이전트 실행과 복구 |
| NGI-16 | W17-MEDIA | 기존 Vision·첨부·음성 경로 확인 | 기준선 감사 | 이미지 생성 및 모델 capability 검증 |
| NGI-17 | W17-CONNECTIONS | MCP 구성 유형과 상태 공용 카탈로그 | MCP UI·프로토콜 계약 | provider·connector 연결 관리 통합 |
| NGI-17A | W17-STRIP | 아래 15개 이름을 대응 기능과 매핑 | 기준선 감사 | 기능별 정책 및 실행 동등성 |
| NGI-18 | W17-POLICY | **PARTIAL**. Gateway Core 프로필 격리, 취소 이후 승인 지연 실행 거부 | Gateway 권한·취소, ActionRegistry 테스트 | 외부 도구, 확장, 자식 Agent 및 자동화 범위 |
| NGI-19 | W17-CONFIG | **PARTIAL**. MCP 쓰기 경로에 기존 설정 백업과 원자적 저장 | 등록·mobile-mcp 설정 보존 계약 | 다른 `config.yaml` 쓰기 경로, Gateway 세션 저장 |
| NGI-20 | W17-RETIRE-GATEWAY | 기존 복구·진단 경로 격리 유지 | `_check_product_no_gateway_spawn`, `_check_gateway_retired_product_surface` | 승인/Connector 동등성 및 복구 호출자 이전 |
| NGI-21 | W17-CLEANUP | 호환 경로 조사 | 아래 호환성 매트릭스 | 대체 검증 후 reverse shim, 진단/호환 코드 정리 |
| NGI-22 | W17-QUALITY | **PARTIAL**. 취소, 동시 턴 거부, 늦은 이벤트 식별 강화. IDE 브리지 자기 복사 및 기동 예외 처리 수정 | 파이프·실제 모델 계약, L4 제품 IDE 9/9 | NIP-09 모델 품질과 기타 WebEngine 종료 조건 |
| NGI-23 | W17-VERIFY | 하단 재현 명령과 증거 | 집중 회귀, FPR13 | 전체 NIP-12 재검증 |
| NGI-24 | W17-INTEGRITY | 기존 Vendor 및 실제 슬롯 해시 검사, 격리 설치·업데이트·손상 복구 | Owned Core release 계약 9/9, L6 실제 모델 4턴 | 전체 설치 프로그램 패키징 |
| NGI-25 | W17-PRODUCT | 제품 IDE 재현 러너와 기존 GUI·설치·빌드 검증 | FPR13, L4 IDE 9/9, L5 GUI 2/2, 로컬 런처 | 전체 UI 기능별 전수 검증 |
| NGI-26 | W17-HANDOFF | 본 문서와 재현 테스트 | 하단 매니페스트 | 구현 후속 단계별 증거 추가 |
| NGI-27 | W17-EXIT | **IMPLEMENTATION PARTIAL** | 본 표 | 외부 MCP 승인/실행 및 Gateway 세션·Connector |

## 기능 흡수 매트릭스

| 기능 | Hermes 경로 | IRIS 정본 또는 현재 대응 | 분류와 실행 증거 | 잔여 |
|---|---|---|---|---|
| Agent / Conversation Loop | `run_agent.py`, `agent/conversation_loop.py` | `engine/agent_entry.py`, `Engine.run_turn`, `_sidecar_main.py` | KEEP-INTERNAL. Owned HELLO 통과 | R-ASSETS-ABSORB 분기별 실행, NIP-09 품질 |
| Model Providers | Vendor `providers/`, Agent 초기화 | `resolve_iris_agent_inference`, `storage/api_providers.py`, UI 모델 선택 | MERGE. 로컬 Ollama 통과 | 유료·원격 제공자 실측 |
| Tool Execution / Search | Vendor `model_tools.py`, `tools/tool_search.py` | `speak_capability.py`, `agent_tool_registry.py`, `engine/tool_surface.py` | REPLACE. FPR13 도구 계약 | MCP 및 확장 검색→실행, 동시 도구 모델 검증 |
| Context Engine / Compression | Vendor `agent/context_engine.py`, `context_compressor.py` | `runtime/context_handoff.py`, `context_archive.py`, Owned 대화 루프 | KEEP-INTERNAL / VERIFY | 압축 및 재시작 뒤 동등성 |
| Memory / `memory` | `tools/memory_tool.py`, Vendor 메모리 플러그인 | IRIS Wiki 및 프로필, `iris_agent_memory_nudge.py` | MERGE 후보. Sidecar `skip_memory=True` 확인 | 모델 조회/갱신/삭제 정책과 데이터 이관 |
| Session / `session_search` | Vendor `tools/session_search_tool.py`, Gateway Session | `runtime/chat_session.py`, `runtime/past_chats.py`, SQLite `storage/conversations.py` | REPLACE. `chat_search_past` 바인딩 | 외부 소유권, 검색 격리, 재시작 복구 |
| Skills / `skills_list`, `skill_view`, `skill_manage` | Vendor `skills/`, `tools/skills_tool.py` | `skill_mcp_dialogs.py`, `github_extension_install.py`, `integrations/hermes-skills/` | MERGE 후보. UI 및 동기화 코드 확인 | 모델 호출, 신뢰 수준, 설치·갱신·삭제 동등성 |
| Plugins / Hook | Vendor `plugins/`, `iris_agent_cli/plugins.py` 계열 | `integrations/hermes-plugins/`, IRIS 확장 설치/정책 | VERIFY. 제품 등록 경로 미증명 | Core Hook 호출 범위, 프로세스 권한과 승인 |
| MCP | Vendor `tools/mcp_tool.py`, `mcp_tool_transport.py`의 Owned Core MCP SDK | `mcp/native_manager.py`, `iris_agent_control_sync.py`, 기존 `apps/mcp_resource.py` | ABSORB 일부. STDIO·HTTP·SSE에서 스키마·리소스·프롬프트 탐색 및 기존 설정 보존 | OAuth, 외부 Binding 승인과 실행, 자동 재연결 |
| Gateway / API Server | `gateway/run.py`, `gateway/platforms/api_server.py` | `system/native_gateway.py`, `system/control_surface.py` | ABSORB 일부. 실제 Owned Engine 호출, 상태·취소·스트리밍. 기존 Gateway는 ISOLATE | 세션 영속화, 승인 이벤트, Connector |
| Messaging / Webhook / Events | `gateway/platforms/`, `webhook*.py`, Gateway 세션 이벤트 큐 | `engine/types.py` 턴 이벤트, 제품 알림 | ABSORB 후보. 터미널 이벤트 계약 | 채널 소유권, Webhook 서명, 재전송/중복 제거 |
| Automation / Cron / Background / `cronjob_manage` | Vendor `cron/`, `tools/cronjob_tools.py` | `runtime/routine_schedule.py`, `routine_runner.py`, `system/routine_wake.py` | MERGE 후보. Routine 스케줄과 직접 모델 경로 확인 | 에이전트 실행, 취소, 재시도, 재시작 및 알림 실측 |
| Planning / `todo_list` / `clarify` | `tools/todo_tool.py`, `tools/clarify_tool.py` | UI 활동/후속 질의, `runtime/turn_followthrough.py` | VERIFY. 행동 증거와 상태 일치 미확인 | 모델 도구, 실행 진행도/일시 정지/재개 |
| Delegation / Multi-agent / `delegate_task` | `tools/delegate_tool*.py`, `agent/delegation_*.py` | `runtime/chat_run_slot.py` 독립 Desktop 턴, `Engine.fork` | ABSORB 후보. 턴 병행은 구현됨 | 부모/자식 관계와 권한, 예산, 취소 |
| Computer Use / `computer_use` | `tools/computer_use/` | `integrations/showui-aloha/`, IRIS Browser, IDE, 에뮬레이터 | VERIFY. 제품별 동작 존재 | 단일 정책과 모델 경로의 동등성 |
| Execute Code / `execute_code` | Vendor 코드 실행 도구 | `runtime/chat_code_exec.py`, `system/execution_runtime.py`, `process_start_plan.py` | REPLACE 후보. 승인 fingerprint 계약 | 인라인 실행 정책/취소와 실제 코드 편집 턴 |
| Vision / `vision_analyze` | Vendor Vision Tool | `infrastructure/local_vision.py`, `runtime/attachment_context.py`, `project.write_image_code` | REPLACE 후보. 파일/모델 경로 확인 | 모델 이미지 관찰, 멀티모달 제공자 검증 |
| Image Generation / `image_generate` | `tools/image_generation_tool.py` | 정본 도구 미확인 | VERIFY | 제공자 capability와 승인 |
| Voice / `text_to_speech` | `tools/tts_tool.py` 및 제공자 | `audio/tts_pipeline.py`, `runtime/voice_intents.py` | REPLACE 후보. 제품 음성 파이프라인 확인 | 에이전트 모델 노출 및 동등성 실측 |
| Connection / `manage_connections` | Vendor CLI 연결 관리, Gateway | API 제공자 Settings, MCP Dialog, Control 상태 | MERGE 후보 | 인증·상태·재연결 통합 |
| Configuration | Vendor `iris_agent_cli/config.py` 및 레거시 env | IRIS 설정/SQLite, `iris_agent_config_path()` | MIGRATE. `mcp_servers` 기존 경로 확인 | 작성자 통합 및 원자성 |
| Lifecycle / Installation / Update / Recovery | Vendor CLI 및 런타임 overlay | `system/iris_agent_install.py`, `iris_agent_update.py`, `infrastructure/agent_runtime.py` | KEEP-INTERNAL / VERIFY. 설치 슬롯과 13개 해시 통과 | 새 Vendor 변경 시 격리 설치와 롤백 재검증 |

표의 `VERIFY`, `후보` 항목은 UI나 소스의 대응 관계만 확인했다. `STRIP_ONLY_NAMES` 15개는 제품 모델 등록 전에 호출 정책과 실제 실행 경로를 각각 검증해야 한다.

## 호환성 이전 매트릭스

| 기존 심볼과 계약 | 현재 정본 | 호출자와 호환 경로 | 제거 조건과 테스트 |
|---|---|---|---|
| `StatelessTurn(transcript, model, cancel, speak_surface, session_id, workspace_id)` | 같은 타입, 선택적 `execution_context` 추가 | Desktop worker가 스냅샷 전달. 설치 모델 확인·Sidecar 테스트는 기존 인수 유지 | 기존 인수 유지. `tests/test_iris_engine_turn_pipe.py`, `tests/test_wave17_turn_context.py` |
| `IrisAgentChatWorker(model, messages, *, target, attempts, session_id, workspace_id, parent)` | 같은 클래스, 선택적 `execution_context` 추가 | `MainWindow._launch_chat_turn_bound`만 제품에서 생성. `_check_execution_context`가 두 계약 확인 | 별도 호환 어댑터 없음 |
| `bind_host_tool_call_meta(*, tool_call_id, request_id)` | 같은 함수에 선택적 host 컨텍스트와 실행/스키마 ID | `Engine._reply_to_tool_request`가 fingerprint를 검증하고 바인딩. `_QtInvoker.run`이 호출 thread context를 전달 | 기존 두 인수 유지. `_check_execution_context`와 실제 Qt 스레드 검사 |
| Stock Gateway CLI 및 `ensure_iris_agent_gateway_running` | 진단/명시적 opt-in 경로 | `agent_runtime.py` guarded call, `_check_hermes_gateway_diagnostics`, recovery CLI의 문자열 진입점 | Native API·세션·승인·취소 실측 및 호출자 이전 전 유지 |
| MCP 설정 및 등록 | `load_mcp_servers_config(home=None)`, `edit_mcp_servers(home=None)` | Composer/MCP Dialog는 `NativeMCPManager.catalog()`. MCP Dialog, GitHub Extension과 mobile-mcp 동기화가 기존 YAML을 공용 변경 경로로 수정 | `test_wave17_native_mcp.py`, `_check_product_no_iris_control_mcp`, `_check_github_extension_install`. 기존 App Resource와 진단 transport 유지 |
| `IrisIdeRuntimeManager.start(project_root_path="")` 및 `IrisIdeLaunchWorker.run()` | 기존 API와 Worker 시그널 | 브리지 원본·대상이 같은 경로이면 복사 생략. 복사 실패나 기동 예외는 기존 `finished_err`와 IDE 오류 슬롯으로 전달 | `_check_iris_ide_runtime`, `_check_fpr_product_gui ide` |

## Gateway 및 MCP 아키텍처

- Desktop은 Worker → `Engine.run_turn` → Internal Sidecar를 호출한다. 실행되는 모델 도구는 호스트가 이름, canonical action, fingerprint, 실행·세션·workspace ID를 확인한 후 Native Dispatcher에 전달한다.
- Qt 슬롯의 스냅샷은 도구 입력과 분리된다. `turn_id`는 논리적 Desktop 턴을, Sidecar wire `turn_id`는 시도별 `run_id`를 나타낸다. `source`와 `run_id`는 일부 도구의 실제 입력 이름이므로 도구 입력에 남아도 실행 권한 필드에 반영되지 않는다.
- 기존 Control API는 `127.0.0.1:8765`의 Bearer 인증과 `/health`, `/v1/ping`, `/v1/catalog`, `/v1/state`, `/v1/invoke`를 사용한다. Native Gateway는 `IRIS_NATIVE_GATEWAY_ENABLED=1`로 같은 리스너에 추가된다. 기존 `:8642` Gateway는 복구·진단 경로다.
- `NativeGateway`는 구성된 로컬 Ollama 대상과 `shared_engine().fork()`를 사용한다. Gateway Sidecar는 Core safe worker 설정으로 사용자 프로필과 플러그인 Hook을 제외하고, `ping`에 한해 기존 Native Dispatcher를 사용한다.
- 현재 인증된 Control Bearer가 Gateway의 한 로컬 principal을 의미한다. 서버가 발급한 Gateway 세션 ID만 조회·재사용할 수 있다. 세션·실행 상태와 이벤트는 프로세스 수명에 한정된다. 실행은 최대 4개, 세션은 최대 64개까지 받는다.
- MCP 연결은 `config.yaml`에 등록된 활성 서버를 명시적으로 선택한 뒤 Owned 슬롯의 MCP SDK를 실행한다. STDIO와 Streamable HTTP/SSE 탐색은 연결 완료 후 프롬프트·리소스·도구 목록을 읽고 정리한다. 요청 재시도는 새 연결로 수행한다. 제품 Sidecar의 기존 MCP refresh/registry 관문은 유지된다.

| 메서드 | 경로 | 계약 |
|---|---|---|
| GET | `/v1/agent/health` | 부팅 및 로컬 모델 설정 준비 검사 |
| GET | `/v1/agent/capabilities` | 세션 수명, 이벤트 형식, 허용 도구, 실행 동시성 |
| POST | `/v1/agent/runs` | `message`, 선택적으로 서버 발급 `session_id`. 202와 실행 ID |
| GET | `/v1/agent/runs/{id}` | 실행 상태 |
| GET | `/v1/agent/runs/{id}/events?after=N` | NDJSON. `seq` 기반 재조회, heartbeat, 누락 구간, 종료 상태 |
| POST | `/v1/agent/runs/{id}/cancel` | 취소 요청 |
| GET | `/v1/agent/sessions/{id}` | 해당 세션에서 성공한 턴의 transcript |

## 검증 인계 매니페스트

| 검증 | 결과 또는 증거 |
|---|---|
| 기준선 및 환경 | `c51d5ba6e88157ad7d9c9fb196a49aa8094e4bfe`, Windows / Python 3.13 호스트 / Owned Core Python 3.14 |
| 검증 소스 지문 | `87c64509eb6767f9817b4894f00064e73ba05ae26547bffb7761c4e68d5a5440`. Git 기준선 대비 변경·추가된 Python 25개를 이름순으로 정렬하고 각 `상대경로 UTF-8 + NUL + 파일 SHA-256 원시 바이트`를 이어 붙여 계산 |
| Vendor 및 설치 슬롯 | `0.1.2+iris.a382af23`, 위 활성 슬롯. 소스 해시 13/13 양쪽 검증 |
| FPR13 기준선 | 15 PASS, 2 FAIL, 8 UNVERIFIED. `.tmp/wave17-baseline/results.json` |
| 기준선 실패 | `fpr_execution_runtime`: Windows 취소 후 하위 프로세스 생존. `fpr_transcript_h1`: Qt 프로세스 종료 코드 `2147483651` |
| FPR13 재검 | 계약 17 PASS, 0 FAIL, 별도 층 8 UNVERIFIED. 루프백 및 Windows 프로세스 권한을 허용한 재실행에서 기준선의 두 실패가 재현되지 않았다. `.tmp/wave17-contracts/results.json` |
| FPR13 실제 모델 포함 | 21 PASS, 0 FAIL, 별도 실행된 L4–L6 4개 포함 전 러너 집계. `.tmp/wave17-live/results.json` |
| 제품 IDE L4 | 초기 `0xC0000409`. Qt 진단으로 브리지 파일 자기 복사 → WinError 32 → 삭제된 Worker 참조를 확인했다. 수정 후 저장소 재현 명령으로 9/9 및 정상 종료. 격리된 프로필과 지정된 테스트 파일에만 승인을 제공한 fixture다. `.tmp/wave17-ide-smoke/results.json`, `.tmp/wave17-ide-smoke/final-run.log` |
| 제품 GUI L5 | Wiki·Browser 및 `process.manage` 승인 거절·허용·stdout 검사 2/2. 두 프로세스 정상 종료 |
| 설치 L6 | 새 격리 설치 → 후보 모델 검사 → 업데이트 → 슬롯 손상 후 롤백, 모델 턴 4/4. `.tmp/wave16-lifecycle/run-429vea0e/evidence.json` |
| 로컬 빌드 | PyInstaller thin launcher 빌드 통과. `.tmp/wave17-build/dist/IRIS.exe` SHA-256 `a21a9e749b234fd8c4cda051aaa8ea4e4fd448e8d3976a4d82148bc829c9310b` |
| 실제 모델 | `python -m iris.system._check_owned_live_hello`로 `gpt-oss:20b` → `IRIS-ACF-HELLO`. `.tmp/owned-live-hello/evidence.json` |
| 집중 검사 | 49/49. Gateway 실제 모델·NDJSON, Native 턴·Qt 컨텍스트, 세 MCP 전송 방식 및 설정 보존, 기존 Sidecar·Control·부팅 검사. `.tmp/wave17-focused-final.xml` |
| 이전 문서와 차이 | FIG-36의 활성 슬롯은 이전 슬롯으로 이동했다. NIP-12의 57/57과 Wave 1.6의 FPR13 17/17은 과거 기록이다. NIP-09 다중 도구/다단계, FPR13 L4 IDE, R-ASSETS-ABSORB는 여전히 잔여다. |
| 관련 기존 계약 | Owned Core release 9/9, GitHub extension, 제품 Gateway spawn 격리, 제품 `iris-control` MCP 미등록, Python compile 및 `git diff --check` |
| 다음 검증 | 모델 → 외부 MCP 도구 실행, Gateway 세션 재시작·승인 이벤트, 전수 NIP-12 및 전체 설치 프로그램 패키징 |

변경 파일은 `iris/engine/{_sidecar_main,runtime,types}.py`, `iris/infrastructure/speak_capability.py`, `iris/mcp/native_manager.py`, `iris/system/{_check_execution_context,_check_iris_ide_runtime,control_surface,execution_context,github_extension_install,iris_agent_control_sync,iris_ide_runtime,native_gateway}.py`, `iris/ui/{_check_fpr_product_gui,_check_local_vibe_smoke,control_bindings}.py`, `iris/ui/chat/{composer_plus_menu,skill_mcp_dialogs}.py`, `iris/ui/window/main_window.py`, `iris/ui/workers/{boot_checks_worker,iris_agent_workers}.py`, `tests/test_wave17_*.py` 네 개와 본 문서다.

격리된 로컬 인수 검사 재현 명령은 다음과 같다. HTTP/MCP와 실제 모델 테스트는 루프백 네트워크와 Windows 하위 프로세스 실행 권한을 사용한다.

```powershell
$env:IRIS_WAVE17_LIVE = '1'
python -m pytest -q tests/test_wave17_turn_context.py tests/test_wave17_control_surface.py tests/test_wave17_native_gateway.py tests/test_wave17_native_mcp.py tests/test_iris_engine_turn_pipe.py tests/test_iris_engine_sidecar.py tests/test_emulator_off_ui.py tests/test_boot_checks_emulator.py
python -m unittest -q tests.test_iris_owned_core_release
.venv/Scripts/python.exe -m iris.system._check_fpr13_runner --contracts-only --out-dir .tmp/wave17-contracts
.venv/Scripts/python.exe -m iris.system._check_fpr13_runner --include-live --out-dir .tmp/wave17-live
.venv/Scripts/python.exe -m iris.system._check_iris_ide_runtime
.venv/Scripts/python.exe -m iris.ui._check_fpr_product_gui ide
.venv/Scripts/python.exe -m iris.ui._check_fpr_product_gui browser
.venv/Scripts/python.exe -m iris.ui._check_fpr_product_gui process
.venv/Scripts/python.exe -m iris.system._check_owned_lifecycle
```
