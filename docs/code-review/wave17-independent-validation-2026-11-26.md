# IRIS Wave 1.7 독립 검증

2026-11-27 KST 최종 갱신.

## A. Independent Validation Report

**Wave 2 Entry · NO-GO.** 로컬 Gateway의 인증된 실제 모델 API, 세 MCP 전송 방식의 발견, 일부 제품 GUI와 Owned Core 슬롯 수명주기는 작동했다. 모델의 등록 MCP 도구 실행, 자연어 복합 도구 실행, Gateway 세션 경계가 진입 조건을 충족하지 못했다. Process 승인 GUI도 실패가 반복됐다.

| 기준 | 관찰 |
|---|---|
| Git HEAD 및 `origin/main` | `c51d5ba6e88157ad7d9c9fb196a49aa8094e4bfe`. Wave 1.7 구현은 작업 트리의 추적 수정 19개와 미추적 7개였다. |
| 최초 작업 트리 | 제품·테스트·빌드 범위 4,097개 파일, SHA-256 `ece2508306341227a7cbe9583887c394087ae71ca52e7b6b605cf60a87dc3f0b`. 구현 추적표의 다른 계산법으로는 변경 Python 25개에서 `87c64509eb6767f9817b4894f00064e73ba05ae26547bffb7761c4e68d5a5440`이 재현됐다. |
| 최종 작업 트리 | 제품·테스트·빌드 범위 4,098개 파일, SHA-256 `717e8c7f3185986b226e2294d4ab8930d967e2c2afb142a0a00c3979ba3fa861`. 보고서와 `.tmp` 실행 결과는 지문 범위 밖이다. [최종 소스 목록](../../.tmp/wave17-independent/final-inventory/source.json) |
| 실행 환경 | Windows x64, 앱 `.venv` Python 3.13.7, Owned Python 3.14.7, Qt Windows 플랫폼, Ollama `gpt-oss:20b`. pytest 9.0.3은 동일 Python의 기존 사용자 사이트에서 가져왔다. |
| Vendor 및 실제 활성 슬롯 | 양쪽 `0.1.2+iris.a382af23`, upstream `a382af23f4c067d23463b5781958684c2cda82bc`. 활성 `iris-agent.slot-272facc0f5fd4b6f`, 이전 `iris-agent.slot-e38f3ea761714c36`. 정상 Probe와 `AIAgent` import가 활성 슬롯의 `venv/Scripts/python.exe`, `run_agent.py`를 확인했다. Core import는 `plugins.web` 부재 경고를 출력했다. |
| 매니페스트와 Lock | Vendor와 활성 슬롯의 `SOURCE_MANIFEST.json` SHA-256 `46505c9e90d5fbe9c12c49223b88e127f0a7902f2eab960b3f2da24cad0e26bc`. 양쪽 13/13 검증. `uv.lock` SHA-256 `c24742f64c04eb32cb340af3ae39258b7ab81a73fc1cbeb761f4cc3f413e2abd`. `legacy_migration_approved=false`. |
| 실행 파일 출처 | PyInstaller 6.22.2 launcher SHA-256 `0bb25f807d8bbfe88937658b03d51374c0fac9642cdfc7f461e1ba189a7ef488`. Inno Setup 6.7.3으로 격리 경로에 빌드한 Setup `0.1.18` SHA-256 `5a0c8c29b765550c4789b5ccf081596645b17fd772a75940c40a269afa9e5c0f`. 제품·Core payload 3,679개와 주요 변경 파일을 최종 작업 트리와 대조했다. 기존 `dist/IRIS.exe`와 `dist/IRIS-Setup.exe`의 최신 소스 출처는 UNVERIFIED다. [빌드 출처](../../.tmp/wave17-independent/setup-provenance.json) |

초기 변경 목록과 파일별 지문을 보존했다. 구현 추적표의 Functional Absorption Matrix, Compatibility Migration Matrix, Validation Handoff Manifest는 대조 자료로 사용했다. 아래 집계는 감사 중 직접 실행한 결과다. [초기 변경 목록](../../.tmp/wave17-independent/initial-status.txt), [초기 소스 목록](../../.tmp/wave17-independent/initial-source.json), [구현 추적표](wave17-implementation-tracker-2026-11-26.md)

| 단계 | 결과 | 독립 관찰 |
|---|---|---|
| V17-01 기능 흡수 | PARTIAL | Owned Agent·기본 Native 경로 실측. 외부 MCP 실행과 15개 기능의 전면 대체 미완료. |
| V17-02 호환성 | PARTIAL | 변경·추가 정의와 문자열 참조를 비교하고 영향 계약을 실행했다. 외부 플러그인 및 배포 패키지 호출자는 범위가 남았다. |
| V17-03 Native Gateway | PARTIAL | 실제 모델 응답과 NDJSON 통과. 같은 프로세스 안의 세션 조회 200, Gateway를 새 인스턴스로 재시작한 뒤 세션과 run 조회 404. 중복 방지·취소·승인 제한 계약 통과. |
| V17-04 MCP | FAIL | STDIO·Streamable HTTP·SSE 발견, 지연된 STDIO 서버 timeout, SDK 직접 호출 통과. 실제 모델의 서버 호출 0/6. SDK 페이지네이션 결함은 재현 후 수정했다. |
| V17-05 Tool Surface | PARTIAL | Native 등록·바인딩·노출 계약 통과. `tool_search` 필수 인수 메타데이터 수정. 일반 모델의 복합 실행 및 MCP 바인딩은 미충족. |
| V17-06 STRIP_ONLY | PARTIAL | 15개 대응 관계는 아래 표에 정리했다. 실제 모델에서의 기능 동등성은 일부만 확인했다. |
| V17-07 메모리·세션 | PARTIAL | 세션·컨텍스트 묶음 136 PASS, 2 FAIL. 레거시 `_log` 기반 노트 검사 2개와 전환 검사 1개는 clean Wave 1.6에서도 동일하게 실패했다. 실제 WebEngine에서 대화 복원은 통과했다. |
| V17-08 스킬·확장·위임 | PARTIAL | 스킬·Routine 검사 74 PASS. GitHub 확장 러너는 성공했으나 Windows에서 건너뛴 MCP 실행 경로가 남았다. 부모·자식 위임 경로는 UNVERIFIED. |
| V17-09 다단계 품질 | FAIL | `tool_choice=auto` 파일 검색·읽기와 혼합 MCP 실행에서 완료 기준 미충족. 개별 시도는 아래 표와 원본 결과에 남겼다. |
| V17-10 보안 일관성 | PARTIAL | Native 계약 4종 및 동결·취소 회귀 통과. 같은 로컬 Gateway 토큰이 공통 권한을 갖고, 외부 MCP·플러그인·자식 정책 통합은 입증되지 않았다. |
| V17-11 안정성 | PARTIAL | sidecar·EOF·취소 묶음 45 PASS. 테스트에서 직접 Qt를 펌프한 두 종료에서 `0xC0000409` 관찰. 정상 Qt 이벤트 루프의 실제 채팅 종료는 한 번 통과. 지속 부하·누수 미측정. |
| V17-12 제품 GUI | PARTIAL | Browser/Wiki와 실제 IDE 9/9. Desktop의 Owned 모델 응답과 대화 복원 확인. Process 승인 GUI는 1/3 성공. |
| V17-13 FPR13 | PARTIAL | 전용 계약 17 PASS. 혼합 실행 23 PASS, 1 FAIL, 1 UNVERIFIED. 별도 `--product-home`에서 L4 PASS. 전체 pytest는 PDF 경로 노출 계약에서 실패했고 Qt 첨부 검사에서 `0xC0000409`로 중단됐다. 두 증상은 clean 기준선에서 재현됐다. |
| V17-14 설치·업데이트·복구 | PARTIAL | Hermes 명령이 없는 격리 환경의 Owned Core 설치·업데이트·손상 복구에서 모델 턴 4/4. 최신 Windows Setup은 빌드했다. 현재 호스트와 분리된 Windows 설치 환경이 없어 Setup 실행과 제품 버전 업데이트는 BLOCKED. |
| V17-15 레거시 폐기 | PASS | 정상 제품 엔트리의 외부 Gateway 기동 및 `iris-control` 등록 방지 계약 통과. 복구·진단 경로는 유지된다. |
| V17-16 빌드·무결성 | PARTIAL | Python 3,332개 컴파일, manifest/lock 검증, thin launcher 및 Inno Setup 빌드, 제한된 비밀 패턴 스캔 통과. 최신 작업 트리 CI는 UNVERIFIED. |
| V17-17 결함 수정 | PARTIAL | P1 두 건 재현 후 수정 및 회귀 확인. P0 MCP 실행과 아래 P1 항목이 남았다. |
| V17-18 증거 패키지 | PASS | 본 문서의 A–F, 테스트 소스, 실행 로그 및 지문 목록. |
| V17-19 Wave 2 | FAIL | 핵심 MCP, 다단계 품질과 세션·GUI 기준 미충족. |
| V17-20 운영 게이트 | NO-GO | 제품 출시 및 외부 공개 검증 미완료. |

## B. Functional Parity Matrix

아래 15개 행은 기존 `STRIP_ONLY_NAMES`와 대응한다. Policy 열의 판단은 확인한 제품 경계에 한정한다.

| 기능 | 기존 Hermes | IRIS 정본과 호출자 | 실제 검증과 Policy | 결과 및 잔여 |
|---|---|---|---|---|
| `vision_analyze` | Vendor `tools/vision_tools.py` 계열 | `infrastructure/local_vision.py`와 `runtime/attachment_context.py`, Desktop 첨부 워커 | 정적 경로 | UNVERIFIED · 실제 이미지 입력과 접근 정책 |
| `image_generate` | Vendor `tools/image_generation_tool.py` | 정상 Tool Surface에서 대응 바인딩 확인 안 됨 | `engine_tool_bindings()` 대조 | FAIL · 제품 모델 접근 경로 |
| `skills_list` | Vendor `tools/skills_tool.py` | `ui/chat/skill_mcp_dialogs.py`, Composer | 로컬 스킬 계약, Desktop 진입점 | PARTIAL · 모델의 스킬 발견 |
| `skill_view` | Vendor `tools/skills_tool.py` | `skill_mcp_dialogs.py`와 설치된 `SKILL.md`, ChatPanel | 로컬 스킬 계약 | PARTIAL · 실제 모델 읽기 및 권한 |
| `skill_manage` | Vendor `tools/skills_tool.py` | `system/github_extension_install.py`, `ChatPanel`, ControlSync Worker | 설치 분류와 상태 계약 | PARTIAL · 비활성·갱신·제거 및 Hook |
| `text_to_speech` | Vendor `tools/tts_tool.py` | `audio/tts_pipeline.py`, `runtime/voice_intents.py`, MainWindow 음성 경로 | 소스와 호출자 대조 | UNVERIFIED · 실제 재생과 모델 도구 동등성 |
| `todo_list` | Vendor `tools/todo_tool.py` | UI 활동, `runtime/turn_followthrough.py` | 정적 대응 후보 | UNVERIFIED · 작업 목록 저장·단계 추적 |
| `memory` | Vendor `tools/memory_tool.py` | IRIS Wiki, 프로필, `iris_agent_memory_nudge.py`, Desktop | Sidecar `skip_memory=True`. 세션·조회 관련 계약만 통과 | PARTIAL · 모델 기억 저장·조회·삭제 동등성 |
| `session_search` | Vendor `tools/session_search_tool.py` | `storage/conversations.py`, `runtime/past_chats.py`, 과거 대화 도구 | 검색·저장 계약과 실제 Desktop 대화 복원 | PARTIAL · Gateway 소유권·영속성·교차 정책 |
| `clarify` | Vendor `tools/clarify_tool.py` | `runtime/turn_followthrough.py`, Desktop 후속 질의 | 정적 대응 후보 | UNVERIFIED · 모델 호출·대기·재개 |
| `execute_code` | Vendor 인라인 실행기 | `runtime/chat_code_exec.py`, `system/execution_runtime.py`, Native Shell/IDE | 실제 Shell 출력, 실제 IDE 고정 승인 및 결과. Native 승인 계약별 검증 | PARTIAL · 인라인·모델 다단계·취소 동등성 |
| `delegate_task` | Vendor `tools/delegate_tool*.py` | `Engine.fork`, `runtime/chat_run_slot.py`, Desktop 채팅 워커 | 독립 Sidecar와 재진입 거절 계약 | PARTIAL · 하위 작업 위임·취소·재귀·권한 미검증 |
| `cronjob_manage` | Vendor `cron/`, `tools/cronjob_tools.py` | `runtime/routine_schedule.py`, `routine_runner.py`, `system/routine_wake.py` | Routine·CLI 계약 | PARTIAL · 실제 예약 모델 실행·재시작 복구 |
| `computer_use` | Vendor `tools/computer_use/` | `iris/browser`, IRIS IDE, Android Emulator, `integrations/showui-aloha` | Browser/IDE 제품 동작. Native 브라우저 의도 및 승인 계약 | PARTIAL · 에뮬레이터/Aloha/통합 모델 실행 |
| `manage_connections` | Vendor CLI·Gateway 연결 관리 | `mcp/native_manager.py`, MCP UI, 제공자 설정 | 등록·상태·전송 인증 계약. 실제 프로토콜 발견 | PARTIAL · 모델 호출, 동적 재접속, OAuth |

추가 영역에서 Agent/Conversation Loop는 `agent_entry` → `Engine` → `_sidecar_main` → Owned `AIAgent`를 확인했다. Context는 `context_handoff`와 `context_archive` 계약을 확인했다. Plugin Hook과 자동화, Gateway, MCP의 권한 결합은 V17-10에서 미검증으로 유지했다.

## C. Compatibility Audit

전체 정의 및 참조 목록은 AST와 `rg`가 생성한다. 정의 목록에는 기준선 대비 Python 정의 112개의 변경·추가 위치가 있다. 같은 이름의 문자열 후보는 실제 호출자와 따로 대조했다. [정의 목록](../../.tmp/wave17-independent/final-inventory/symbols.json), [참조 목록](../../.tmp/wave17-independent/final-inventory/symbol-references.txt)

| 심볼 또는 계약 | 기존 호출자와 현재 경로 | Runtime Import / Packaging |
|---|---|---|
| `StatelessTurn`, `IrisAgentChatWorker.__init__` | 기존 위치 인수를 유지하고 선택적 `execution_context`를 받는다. MainWindow, 모델 설치 검증, Engine Pipe fixture 호출을 대조했다. | PASS · 실제 Sidecar와 GUI 워커. 최신 Setup payload의 제품 소스 일치 확인. |
| `Engine._reply_to_tool_request`, `_write_turn`, `bind_host_tool_call_meta`, `_QtInvoker` | Qt Worker → Engine → ContextVar → Native Dispatcher 경로. 호스트가 턴 및 스키마를 동결한다. Sidecar 메시지 ID를 왕복한다. | PASS · 컨텍스트/파이프/동결 계약. |
| `ControlSurface.start/stop`, `start_control_surface` | MainWindow의 `_on_intro_finished`, Companion 및 기존 `/v1/invoke` 유지. Gateway는 동일 루프백 서버에 선택적으로 붙는다. | PARTIAL · 바인딩 실패와 HTTP 비활성 계약 통과. 승인 UI 실패. |
| `load_mcp_servers_config`, `edit_mcp_servers`, `ensure_mcp_in_config`, `NativeMCPManager` | Composer/McpDialog 및 GitHub 확장 등록은 공용 설정을 사용한다. mobile-mcp 등록과 설정 보존을 확인했다. | PARTIAL · 실제 Owned SDK 발견. 기존 App Resource와 모델 연결은 UNVERIFIED. |
| `list_iris_agent_mcps`, `add_mcp_server`, `list_iris_agent_mcp_names` | ChatPanel과 Composer가 기존 표시와 등록 함수 이름을 유지한다. | PASS · 설정·표시 계약 범위. |
| `IrisIdeRuntimeManager.start`, `IrisIdeLaunchWorker.run` | 기존 IDE 흐름과 Worker 시그널. `finished_err`와 브리지 복사 예외를 관련 검사와 실제 IDE 흐름에서 대조했다. | PASS · IDE 제품 경로 9/9. |
| `assemble_iris_model_tools`, `dispatch_iris_bridge`, `engine_tool_bindings` | Sidecar 바인딩과 Host `_reply_to_tool_request`, Core executor의 브리지 처리. `tool_search`의 메타데이터 수정은 승인 권한과 스키마 검증 경계를 유지한다. | PARTIAL · 계약/바인딩 PASS, 모델 품질과 모든 unwrap 분기 UNVERIFIED. |
| `ensure_iris_agent_gateway_running`, `iris-control`, `:8642` | 명시적 복구·진단 및 호환 CLI/정책 경로. 제품 경로의 레거시 기동 차단 계약을 다시 실행했다. | PASS · 정상 경로 범위. 외부 확장·과거 설치본 패키징 UNVERIFIED. |

설치 및 복구 모듈의 Import와 핵심 호출은 Owned 슬롯 실측으로 대조했다. 외부 플러그인 문자열 진입점 전수, 모든 GUI 신호 조합, 과거 DB 전체 마이그레이션 및 설치 패키지의 clean Windows 실행은 UNVERIFIED다.

## D. Product Validation Matrix

실행 위치는 저장소 루트다. `python`은 앱 `.venv/Scripts/python.exe`다. 실모델 단계는 루프백을 사용할 수 있는 Windows 세션에서 실행했다. 모델·GUI 데이터는 폐기 가능한 별도 프로필을 썼다.

| 시나리오 | 층·환경·모델 | 실행과 기대값 | 실제 결과·횟수 | 증거 |
|---|---|---|---|---|
| Gateway | L2+L3, 로컬 HTTP와 `gpt-oss:20b` | `pytest tests/test_wave17_native_gateway.py tests/test_wave17_control_surface.py`에서 auth, NDJSON, 완료·취소 및 실제 응답. `gateway-restart`의 기대값은 재시작 뒤에도 세션과 run 조회 200 | 처음 5/5. 최종 집중 묶음 18/18. 재시작 독립 시도 1회에서 모델 응답, 401 두 건, 시작 전후 health 503/200, heartbeat 2회, 정상 종료 0.308초를 확인. 재시작 뒤 세션·run 404로 지속성 FAIL. | [초기](../../.tmp/wave17-independent/v17-03.log), [최종](../../.tmp/wave17-independent/v17-final-focused.log), [재시작](../../.tmp/wave17-independent/gateway-restart/gateway-result.json) |
| MCP 발견 | L2+L3, 테스트 서버, Owned SDK | `pytest tests/test_wave17_native_mcp.py`로 등록·비활성·설정 보존·세 전송 방식·인증 헤더·resources/prompts. `mcp-timeout`으로 지연된 STDIO 서버 확인 | 초기 7/7. 페이지 계약 추가 후 FAIL 1건, 수정 후 PASS 7/7. 2초 제한 STDIO 시도 1회 `timeout`, SDK 정리 포함 경과 4.848초. | [재현](../../.tmp/wave17-independent/v17-04-pagination-before-host.log), [재검](../../.tmp/wave17-independent/v17-04-pagination-after.log), [MCP 타임아웃](../../.tmp/wave17-independent/mcp-timeout/mcp-timeout.json) |
| MCP 모델 호출 · B/C | L3, STDIO, `gpt-oss:20b`, auto | `python -m scripts.validate_wave17 mcp --attempts 5 --out ...`에서 Native 발견과 실제 SDK 호출, 모델이 생성 코드를 회수 | FAIL · 최초 0/5, 수정 후 0/1. SDK 직접 호출 6/6, 모델의 서버 호출 0건. Native+MCP 및 여러 MCP 순차/동시 완료는 UNVERIFIED. | [5회 결과](../../.tmp/wave17-independent/mcp-model-final/mcp-results.json), [수정 후 실행](../../.tmp/wave17-independent/mcp-model-after/mcp-results.json) |
| Native 복합 · A 전반부 | L3, 첨부된 격리 폴더, `gpt-oss:20b`, auto | `python -m scripts.validate_wave17 native --attempts 5 --out ...`에서 탐색→읽기→정확한 값 보고 | FAIL · 최초 0/5, 수정 후 0/5. 스키마가 잘못된 인수를 거부했다. 모델 직접 수정→실행→보고까지는 UNVERIFIED. | [초기 결과](../../.tmp/wave17-independent/native-model/native-results.json), [수정 후 결과](../../.tmp/wave17-independent/native-model-after/native-results.json) |
| Browser→저장 · D | L5, 실제 Qt WebEngine | `python -m iris.ui._check_fpr_product_gui browser`에서 Wiki/Browser 및 로컬 탐색 | PARTIAL · Browser 개별 기능 통과. 모델이 확인 내용을 파일에 저장하는 체인은 UNVERIFIED. | [GUI 로그](../../.tmp/wave17-independent/v17-12-browser.log) |
| IDE 작업 · E | L4, 실제 Qt/MainWindow, Theia | `python -m iris.ui._check_fpr_product_gui ide` 및 FPR13 `--product-home`에서 폴더 열기, 파일 작성, 실행·출력 및 IDE Companion | PASS · 지정 파일에 한정된 승인 fixture로 9/9. 모델 주도 IDE와 Dirty File 전수는 UNVERIFIED. | [IDE 로그](../../.tmp/wave17-independent/v17-12-ide.log), [제품 홈 로그](../../.tmp/wave17-independent/fpr13-product-home-retry/logs/ide_product_control.log) |
| 계획·복구 · F/G | L2와 실제 실패 턴 | 도구 오류 계약과 실행 추적 대조 | PARTIAL · 일부 도구 오류에서 잘못된 인수/출력이 그대로 남았다. 실제 계획 전 과정과 복구 성공은 UNVERIFIED. | [모델 시도](../../.tmp/wave17-independent/native-model/native-results.json) |
| 취소·동시성 · H/I | L2/L3 계약, 격리 데이터 | Pipe·Session·Runtime 계약에서 취소와 재진입 차단, 상태 복원 | PARTIAL · 런타임 검증 묶음 45/45. 장시간 실모델 취소→후속 턴과 실제 멀티세션 부하는 UNVERIFIED. | [안정성 묶음](../../.tmp/wave17-independent/v17-11-pytest.log) |
| 위임 · J | 소스/계약 | Worker의 `Engine.fork`와 위임 도구 바인딩 점검 | UNVERIFIED · 모델 위임, 권한 상속, 취소 전파, 자식 정리. | [정의 목록](../../.tmp/wave17-independent/final-inventory/symbols.json) |
| Desktop Chat | L5, 실제 Qt, `gpt-oss:20b` | `python -m scripts.validate_wave17 gui-chat --out ...`에서 Picker, Owned Worker, 정확한 최종 응답, 대화 복원, 정상 닫기 | PARTIAL · 첫 fixture는 준비 대기 실패. 직접 이벤트를 펌프한 두 종료에서 `0xC0000409`. 정상 Qt 루프 재검 1회에서 기능과 종료 성공. 콘텐츠 스트리밍 계측은 0회로 UNVERIFIED. | [직접 펌프 증거](../../.tmp/wave17-independent/gui-chat-fault/gui-chat.json), [정상 Qt 루프 증거](../../.tmp/wave17-independent/gui-chat-qt-loop/gui-chat.json) |
| Process 승인 GUI | L5, 실제 Qt | `python -m iris.ui._check_fpr_product_gui process`에서 Skip→거부, Run→승인·stdout | PARTIAL · Wave 1.7 첫 두 시도 타임아웃, 클릭 전달을 계측한 세 번째 시도 PASS. Clean Wave 1.6 대조 1회 PASS. | [첫 실행](../../.tmp/wave17-independent/v17-12-process.log), [FPR13 재실행](../../.tmp/wave17-independent/fpr13-live-gui-lifecycle/logs/process_approval_gui.log), [세 번째 시도](../../.tmp/wave17-independent/v17-12-process-third.log), [clean 기준선](../../.tmp/wave17-independent/v17-12-process-clean-baseline.log) |
| Email/Calendar | L2, 격리 fixture | FPR13 Email Compose 계약, 상태 확인 | PARTIAL · 초안 계약 PASS. 실제 제품 계정 읽기·일정 생성 UI는 UNVERIFIED. | [FPR13 계약 결과](../../.tmp/wave17-independent/fpr13-contracts/results.json) |
| FPR13 | L1–L6, Windows, `gpt-oss:20b` | `--contracts-only`, `--include-live --include-gui --include-lifecycle`, `--product-home` | 계약 17 PASS. 혼합 실행 23 PASS, 1 FAIL, 1 UNVERIFIED. 실모델 HELLO·Shell, Browser, L6가 통과했고 Process 승인이 실패했다. 별도 `--product-home`은 첫 호출에서 두 홈이 같아서 거절됐고, 분리한 재시도에서 L4 포함 18 PASS, 0 FAIL. | [계약](../../.tmp/wave17-independent/fpr13-contracts/results.json), [혼합 실행](../../.tmp/wave17-independent/fpr13-live-gui-lifecycle/results.json), [제품 홈 첫 시도](../../.tmp/wave17-independent/v17-13-product-home.log), [제품 홈 재시도](../../.tmp/wave17-independent/fpr13-product-home-retry/results.json) |
| 전체 pytest | L1–L3 혼합, Windows, 폐기용 프로필 | `python -m pytest tests`, 실패 위치 확인, Qt bootstrap 재시도 및 기준선 대조 | FAIL · PDF 첨부 모델 payload에 절대 경로 포함, OCR 오류 분류 검사 실패. Qt 첨부 검사에서 Windows `0xC0000409`로 3회 중단돼 전체 집계 미완료. PDF 경로 실패와 동일한 Qt 첨부 검사 종료 오류는 clean 기준선에서도 재현. | [최초 실패 확인](../../.tmp/wave17-independent/v17-13-full-pytest-first-failure.log), [Qt 재실행](../../.tmp/wave17-independent/v17-13-full-pytest-qt-bootstrap.log), [PDF 기준선](../../.tmp/wave17-independent/v17-13-attachment-baseline.log), [Qt 기준선](../../.tmp/wave17-independent/v17-13-qt-attachment-baseline.log) |
| Owned 수명주기 | L6, 새 프로필, `gpt-oss:20b` | `_check_owned_lifecycle`에서 external CLI 미발견, 설치, 후보 턴, 업데이트, 슬롯 손상, 롤백, 데이터 유지 | PASS · 실제 Core materialization과 모델 턴 4/4, 슬롯 손상 뒤 복구 및 테스트 데이터 보존. 전체 Windows Setup과 제품 버전 업데이트는 BLOCKED. | [L6 로그](../../.tmp/wave17-independent/fpr13-live-gui-lifecycle/logs/installer_lifecycle.log), [수명주기 증거](../../.tmp/wave16-lifecycle/run-k_a64ou4/evidence.json) |
| Build & Source | 빌드, Windows | `PyInstaller ... IRIS.spec`, 격리 staging의 `build_iris_setup.ps1 -NoPublish`, Python 컴파일, 파일명만 출력하는 비밀 패턴 검사 | thin launcher 및 Setup `0.1.18` PASS, 패키지 체크섬 일치, 서명 `NotSigned`. 앱 Python 909개와 Owned Python 2,423개 컴파일 PASS. 지정 패턴 후보 0개. GitHub 조회는 기준선 PR 워크플로 0개, 작업 트리 CI는 UNVERIFIED. | [launcher](../../.tmp/wave17-independent/v17-16-launcher-build.log), [Setup](../../.tmp/wave17-independent/v17-16-setup-build.log), [출처](../../.tmp/wave17-independent/setup-provenance.json), [컴파일](../../.tmp/wave17-independent/v17-16-compile.log) |

측정한 모델은 `gpt-oss:20b` 한 종이다. 파일 탐색과 MCP 시도의 개별 응답 시간, 실패 도구 수, 최종 이벤트는 JSON에 기록했다. 준비 단계에서 SDK 1.x API와 2.x 결과 속성 차이로 중단된 세 번의 fixture 시도도 로그에 있다. 모델 비교, 장기 실행 취소 지연과 메모리 사용량은 측정하지 않았다. [초기 fixture](../../.tmp/wave17-independent/v17-04-model.log), [SDK 전환](../../.tmp/wave17-independent/v17-04-model-sdk2.log), [결과 형식](../../.tmp/wave17-independent/v17-04-model-sdk2-direct.log)

## E. Security & Independence Audit

| 경계 | 검증 결과 |
|---|---|
| Gateway authority | 루프백에만 바인딩한다. 인증 없음·잘못된 토큰 401 실측. 잘못된 세션 ID 404, 권한 필드 400, 같은 세션 활성 run 중복 409 계약 PASS. 공용 토큰과 Gateway principal을 쓴다. 주체별 세션·run 분리, 토큰 만료·회전·재사용 방어, 지속성과 승인 이벤트는 미충족. 포트 충돌 시 Desktop Native 레지스트리 유지 계약은 PASS. |
| Agent authority | 정상 Desktop과 Gateway는 Owned Engine을 호출한다. 설치된 외부 Hermes CLI는 개발 PC PATH에 남아 있다. L6 격리 실행 PATH에는 없었고, 실제 AIAgent 경로와 슬롯 매니페스트가 Owned 출처를 확인했다. |
| Tool authority | Native 스키마·동결·권한 주장 무시·승인 없이 실행 거부·취소 후 dispatch 방지 계약이 통과했다. Request Approval, 실행 경로 정책, 단일 SpeakTools 권위, 기존 Native Hermes registry 비활성 검사 4/4. 승인 만료·재사용 및 plan 변경은 기존 ledger 계약 범위의 증거다. Junction, 별도 인라인 실행 분기, 장시간 작업 경합, 사용자별 데이터 보호는 전체 E2E UNVERIFIED. |
| MCP authority | 등록·활성 확인과 실제 전송 발견, 인증 헤더 전달, 기본 `iris-control` 미등록을 확인했다. MCP→모델 dispatcher가 연결되지 않아 승인, 이름 충돌, schema 교체, 최초 인증 실패·재연결, 결과 주입, 앱 리소스, mobile-mcp와 GitHub 확장 MCP의 제품 정책은 UNVERIFIED. |
| Plugin·자동화·Delegation | 스킬·등록·Routine 기본 계약을 확인했다. Plugin Hook과 Child Agent가 같은 policy를 적용하는지, 취소·예산·재귀·자식 정리 및 외부 자동화 경계는 UNVERIFIED. |
| 로그와 비밀정보 | fixture에는 합성 코드와 테스트 자격증명만 사용했다. 제한된 소스 패턴 스캔은 후보 파일이 없었다. 실제 제공자·외부 연동의 비밀 누출 시험 및 전체 도구 출력의 주입 방어는 UNVERIFIED. |
| 레거시와 복구 | 정상 Gateway spawn 방지, Legacy 단리, `iris-control` 설정 제거, Owned 엔트리 검사 통과. Vendor 내부 유래 모듈, 명시적 진단·복구와 이전 슬롯은 보존한다. Desktop 채팅이 Native HTTP 비활성 상태에서 실제 Owned 모델로 응답했다. |

[권한 검사](../../.tmp/wave17-independent/v17-10-security-_check_request_approval.log), [실행 정책](../../.tmp/wave17-independent/v17-10-security-_check_execution_policy.log), [레거시 격리](../../.tmp/wave17-independent/v17-15-_check_gateway_legacy_isolated.log)

## F. Wave 2 Entry Verdict

| # | 필수 조건 | 판정 |
|---|---|---|
| 1 | 정상 Agent Runtime의 Owned 단일 경로 | PASS · 확인한 Desktop과 Gateway |
| 2 | 외부 Hermes 설치 없이 핵심 기능 실행 | PARTIAL · Owned 수명주기·실제 모델, MCP 및 통합 기능 잔여 |
| 3 | 정상 경로의 Hermes Gateway 퇴역 | PASS · 실행 경로 및 회귀 검사 |
| 4 | Native Gateway 실제 Agent API | PASS · 인증된 로컬 요청과 실제 모델 응답, 세션·권한 확장은 별도 미충족 |
| 5 | 실제 모델 MCP 발견과 실행 | FAIL · 서버는 작동하고 모델 호출 0건 |
| 6 | Native/MCP 통합 정책 | FAIL · 실제 MCP dispatch·approval 연결 부재 |
| 7 | 기존 유효 기능 대체 | PARTIAL · B 참조 |
| 8 | 미등록·권한 우회 차단 | PARTIAL · Native 계약 검증, 외부 실행 층 잔여 |
| 9 | 실제 다중 도구·다단계 완료 | FAIL · 자연어 auto 기준 미충족 |
| 10 | 핵심 Desktop GUI | PARTIAL · Browser/IDE와 대화 복원, Process 승인과 종료 문제 |
| 11 | 호출자 호환성 | PARTIAL · 핵심 Import/Worker 계약, 배포 패키지와 확장 경로 잔여 |
| 12 | Clean Install/Update/Recovery | PARTIAL · Owned 슬롯 범위 실측, Windows 제품 설치와 제품 버전 업데이트 BLOCKED |
| 13 | 최종 소스 핵심 회귀 | PARTIAL · 계약 17/17, Gateway/MCP/컨텍스트 집중 18/18, FPR13의 GUI 승인 실패 및 기존 Qt 첨부 회귀로 전체 pytest 중단 |
| 14 | 미해결 P0 0건 | FAIL · 실제 모델 MCP 실행 경로 |
| 15 | Wave 2에 영향을 주는 P1 0건 | FAIL · Gateway 세션/승인, 복합 실행과 GUI 안정성 |

| 등급 | 결함과 처리 |
|---|---|
| P0 · 미해결 | 정상 모델이 등록된 외부 MCP를 실행하지 못한다. Native Tool Surface에 등록·발견 결과를 권한 있는 실행 바인딩으로 전달하는 경로와 승인·변경 검증이 필요하다. |
| P1 · 수정 | MCP SDK 2.x의 `next_cursor`를 읽도록 바꿨다. 첫 페이지 뒤의 도구가 사라지던 회귀를 재현하고 실제 STDIO 두 페이지 및 7개 검사로 검증했다. |
| P1 · 수정 | `tool_search`가 실제로 필요한 필드 이름을 반환하도록 바꿨다. `search_files`의 `root`, `query` 계약은 실패에서 통과로 전환됐다. 수정은 모델 작업의 전체 완료 판정을 변경하지 않는다. |
| P1 · 미해결 | Gateway는 프로세스 안에서만 세션과 run을 갖고, 공용 토큰과 ping 도구 범위를 사용한다. 영속 세션·개별 권한과 승인 요청·결과를 이어주는 제품 계약이 필요하다. |
| P1 · 미해결 | `tool_choice=auto` 파일 탐색→읽기 실측에서 인수 검증 거부 및 답변 grounding 실패. 시도 로그의 동작으로만 판정했다. |
| P1 · 미해결 | Process 승인 GUI는 두 번의 클릭 후 타임아웃을 남겼고 세 번째에는 통과했다. 클릭 전달 실패의 원인은 좁히지 못했다. 정상 Qt 루프에서 채팅과 종료가 통과했으며, 다른 Harness에서 발생한 종료 오류의 원인은 UNVERIFIED다. |
| P2 · 미해결 | 과거 노트·대화 전환 검사는 레거시 `_log`를 확인하며 clean Wave 1.6에서 동일하게 실패한다. 실제 WebEngine 대화 복원을 별도로 확인했다. |
| 기준선 결함 | PDF 첨부의 합성 로컬 경로가 모델 payload에 포함된다. clean Wave 1.6에 같은 증상이 있다. 실제 외부 전송은 UNVERIFIED다. Qt 첨부 전체 검사의 프로세스 종료 오류도 기준선에서 반복됐다. |

**운영 게이트.** Production Readiness와 Public Release는 NO-GO다. 전체 사용자 마이그레이션과 복구 백업 영구 제거는 UNVERIFIED다. Public Network Exposure는 NO-GO이며 실측 범위는 루프백이다.

**재현.** [독립 검증 러너](../../scripts/validate_wave17.py), [회귀 검사](../../tests/test_wave17_native_mcp.py), [Tool Surface 계약](../../iris/engine/_check_tool_surface.py), [기존 FPR13 러너](../../iris/system/_check_fpr13_runner.py). 증거는 `.tmp/wave17-independent`에 보관했다. 파일별 지문과 등급은 이 실행의 소스 범위에 적용된다.

```powershell
.venv/Scripts/python.exe -m scripts.validate_wave17 gateway-restart --out .tmp/w17-repro-gateway
.venv/Scripts/python.exe -m scripts.validate_wave17 mcp-timeout --out .tmp/w17-repro-mcp-timeout
.venv/Scripts/python.exe -m scripts.validate_wave17 mcp --attempts 5 --out .tmp/w17-repro-mcp-model
.venv/Scripts/python.exe -m scripts.validate_wave17 native --attempts 5 --out .tmp/w17-repro-native
.venv/Scripts/python.exe -m scripts.validate_wave17 gui-chat --out .tmp/w17-repro-gui-chat
.venv/Scripts/python.exe -m scripts.validate_wave17 gui-product-home --out .tmp/w17-repro-product-home
```
