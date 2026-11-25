# Wave 1.3 Native Tool Unification — 완료/핸드오프 (NTU-12)

| 항목 | 내용 |
|---|---|
| 문서 번호 | NTU-12 |
| 작성일 | 2026-11-25 |
| 관련 | Unify IRIS native tool routing · Stage1 authority · Stage2 fingerprint · NTU-05 Hermes guard |
| 대상 | sidecar native bridge · parent tool reply · speak_capability bindings |
| 목적 | Wave 1.3 계약 닫힘 여부 판정 및 PROMPT 02 핸드오프 |
| Baseline HEAD | `1ab0452` (작업 전; 현재도 HEAD, 변경은 uncommitted) |
| Branch | `main` (커밋·push 없음) |

## 1. 결론

Wave 1.3는 **제품 권한(native authority) + 신뢰 바인딩(fingerprint) + Hermes registry 차단**까지 로컬 코드·계약 체크·설치 엔진 증명으로 닫혔다. 이어서 verify 런처로 Iris를 기동해 **GUI 실채팅 툴 턴**까지 증명했다.

**판정: GO** — cid `400`에서 모델이 `terminal`을 호출했고, sidecar/host 모두 `TOOL_ROUTE … action=shell.run owner=iris`를 남겼다. 증거: `.iris_light_test_tmp/verify-iris/wave13-ntu/gui_tool_turn.json`.

원칙: **Prove It Works** — `_check_*` 재실행 + `live_engine_proof.json` + 라이브 `TOOL_ROUTE`/`TOOL_CALL` 로그.

## 2. 확인한 사실

| 항목 | 결과 | 근거 |
|---|---|---|
| HEAD | `1ab0452` | `git rev-parse HEAD` |
| Uncommitted 변경 | 기대 파일 집합과 일치 | `git status` / `git diff --stat` |
| `_check_native_tool_hermes_disabled` | ok `blocked=apply_patch,clarify,patch` | exit 0 (재실행) |
| `_check_absorbed_tool_wire` | ok `home_n=115 ide_n=115` | exit 0 |
| `_check_native_tool_binding` | ok | exit 0 |
| `_check_tool_contract` | ok schema 115/115 | exit 0 |
| `_check_absorbed_tool_aliases` | ok | exit 0 |
| `tests.test_iris_engine_runtime` | 13 OK | exit 0 |
| `_check_agent_turn_tools` | ok | exit 0 |
| 설치 엔진 증명 | `ok=true`, terminal→`shell.run`, absorbed/strip→`TOOL_NOT_AVAILABLE` | `.iris_light_test_tmp/verify-iris/wave13-ntu/live_engine_proof.json` |
| GUI 툴 턴 | PASS — `terminal`→`shell.run` owner=iris, cid=400, user=1600/asst=1601 | `gui_tool_turn.json` + `agent.log`/`turn_end_watch.log` |

### 변경 파일 (측정)

| 경로 | 상태 |
|---|---|
| `iris/engine/_sidecar_main.py` | modified |
| `iris/engine/runtime.py` | modified |
| `iris/engine/types.py` | modified (`session_id`/`workspace_id` on `StatelessTurn`) |
| `iris/infrastructure/speak_capability.py` | modified |
| `iris/infrastructure/_check_absorbed_tool_wire.py` | modified |
| `iris/infrastructure/_check_native_tool_binding.py` | **new** |
| `iris/infrastructure/_check_native_tool_hermes_disabled.py` | **new** |

diff 규모(추적 파일): +472 / −62 (5 tracked); untracked 체크 2개.

## 3. 구조

요청이 모델 툴 이름에서 Iris 액션·디스크/UI까지 가는 경로:

```text
AIAgent turn (sidecar)
  └─ model_tools.handle_function_call  ← product dispatch (Stage1)
       ├─ binding snapshot 없음 / unknown name
       │    └─ TOOL_NOT_AVAILABLE  ★분기 A
       └─ EngineToolBinding hit
            └─ _request_native_tool (+ _NATIVE_TOOL_LOCK, stdin 직렬)
                 └─ emit tool_request {model_tool_name, fingerprint, turn/session/workspace}
                      └─ Engine._read_turn_events
                           └─ Engine._reply_to_tool_request (Stage2)
                                ├─ fingerprint/action/turn/session/workspace 불일치
                                │    └─ tool_binding_error  ★분기 B
                                └─ parent-derived canonical_action only
                                     └─ _tool_handler(action, args) → Control/Runtime
                                          └─ tool_result → sidecar stdin

우회 경로 (제품 마커 있을 때 막음 · NTU-05):
  tools.registry.dispatch(absorbed|STRIP_ONLY|INTERNAL_ALIASES)
    └─ _guard_hermes_registry_dispatch → TOOL_NOT_AVAILABLE  ★분기 C
       (Hermes handler 미실행)

MCP refresh:
  refresh_agent_mcp_tools + agent._iris_native_tool_bindings
    └─ _guard_native_tool_refresh → no-op set()  ★분기 D
```

도메인 형태: `EngineToolBinding(model_name, canonical_action, description, input_schema, fingerprint)` — `engine_tool_bindings(surface)`가 home/IDE 스키마에서 파생. 부모는 sidecar가 보낸 액션 문자열을 믿지 않고, surface 기준 바인딩에서 다시 고른 `canonical_action`만 invoke한다.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 예전에 막지 못한 이유 |
|---|---|---|
| `_install_iris_engine_tools` | immutable snapshot 설치, `handle_function_call` 교체, IRIS `registry.register` 없음, MCP skip | Core가 Hermes registry/handler로 흡수 툴을 직접 실행 |
| `_request_native_tool` + `_NATIVE_TOOL_LOCK` | request/response를 stdin 한 트랜잭션으로 직렬화 | 동시 툴 호출 시 stdin 교차 |
| `_guard_hermes_registry_dispatch` | absorbed+strip+alias → `TOOL_NOT_AVAILABLE` | `handle_function_call`만 갈아도 `registry.dispatch` 우회 가능 |
| `_guard_native_tool_refresh` | native 마커 agent에서 MCP refresh 무력화 | refresh가 Core 툴을 다시 심음 |
| `EngineToolBinding` / `engine_tool_bindings` | surface별 fingerprint(sha256) 산출 | 이름만 맞춰도 스키마/액션 위조 가능 |
| `Engine._reply_to_tool_request` | fingerprint·turn·session·workspace 검증 후 parent action만 실행 | sidecar가 보낸 `name`을 그대로 invoke |
| `StatelessTurn.session_id/workspace_id` | 바인딩 검증에 쓸 신원 필드 | 턴 신원 없이 fingerprint만으로는 session 스푸핑 여지 |
| `_check_native_tool_*` / wire | Stage1·2·NTU-05 회귀 잠금 | 계약 체크 없음 |

하지 않은 일: PROMPT 02/03 구현, catalog에 `process.manage`/`project.apply_patch` 기대 추가(기존 결함 유지), sidecar 116 vs 115 스키마 기대 완화, 커밋/push. GUI Shell Box DOM 가시성 픽셀 검증은 하지 않음(라우팅 권위는 로그로 증명).

## 5. 개선안 (구조상 빈 자리만)

| 빈 자리 | 다음 |
|---|---|
| catalog 기대 누락 | `process.manage` / `project.apply_patch` expectations (사전 결함; 이번 웨이브에서 약화 금지) |
| sidecar suite 116 vs 115 | 스키마 카운트 기대 불일치 (사전 결함) |
| 모델 답변 품질 | 툴은 돌았으나 assistant 본문이 약함 — Wave 1.3 권위와 별개 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Capability / attestation tokens (SPIFFE-like) | 프로세스 간 바인딩 증명 | fingerprint+turn 신원으로 충분, 외부 IAM 과다 |
| OpenAI function-calling tool router 패턴 | name→handler 표 | 제품이 이미 `engine_tool_schemas`·absorbed aliases 보유 |
| MCP tool refresh 파이프라인 | 동적 툴 재등록 | native authority와 충돌 — 가드로 차단만 |

찾지 못함: Wave 1.3 전용 오픈소스 “Hermes registry neutralize” 패키지. 제품 가드가 최소 해법.

## 7. 테스트 명령 + 결과

본 세션 재실행 (모두 exit 0):

```powershell
.venv\Scripts\python.exe -m iris.infrastructure._check_native_tool_hermes_disabled
# → native_tool_hermes_disabled ok blocked=apply_patch,clarify,patch

.venv\Scripts\python.exe -m iris.infrastructure._check_absorbed_tool_wire
# → absorbed_tool_wire ok home_terminal=True ide_terminal=True home_n=115 ide_n=115

.venv\Scripts\python.exe -m iris.infrastructure._check_native_tool_binding
# → native_tool_binding ok

.venv\Scripts\python.exe -m iris.infrastructure._check_tool_contract
# → tool_contract ok (engine_schema_home_count=115, ide_count=115)

.venv\Scripts\python.exe -m iris.infrastructure._check_absorbed_tool_aliases
# → absorbed_tool_aliases ok

.venv\Scripts\python.exe -m unittest tests.test_iris_engine_runtime
# → Ran 13 tests … OK

.venv\Scripts\python.exe -m iris.ui._check_agent_turn_tools
# → agent turn tools ok
```

설치 엔진 증명 (부모 측정, 재확인):

- 경로: `.iris_light_test_tmp/verify-iris/wave13-ntu/live_engine_proof.json`
- `handle_function_call(terminal)` → `via=native`, `action=shell.run`
- `registry.dispatch` on `apply_patch`/`clarify`/`process_manage`/`skills_list` → `TOOL_NOT_AVAILABLE`
- registry 파일: `~\.iris-light\agent\hermes-agent\tools\registry.py`

GUI 실툴 턴 (verify 런처 PID, 종료 후 마커 삭제):

- 경로: `.iris_light_test_tmp/verify-iris/wave13-ntu/gui_tool_turn.json`
- `chat.new_session` → cid `400`; `chat.send` terminal echo 프롬프트
- DB: user `1600` / assistant `1601` 동일 cid
- `agent.log`: `TOOL_ROUTE model_tool_name=terminal action=shell.run owner=iris` + `TOOL_CALL` + `tool terminal completed`
- `turn_end_watch.log`: host `TOOL_ROUTE … terminal action=shell.run owner=iris`

## 8. 남은 결함

| 결함 | 심각도 | 비고 |
|---|---|---|
| sidecar suite 116 vs 115 schema expectation | 기존 | 약화 금지 |
| catalog missing `process.manage` / `project.apply_patch` expectations | 기존 | 약화 금지 |
| 라이브 턴 assistant 본문 빈약 | 낮음 | 툴 라우팅과 별개; 모델 응답 품질 |

## 9. 판정

| 축 | 상태 |
|---|---|
| Stage1 native authority | PASS (코드+체크+설치증명) |
| Stage2 trusted binding | PASS (코드+`_check_native_tool_binding`) |
| NTU-05 Hermes disable | PASS (코드+체크+설치증명) |
| NTU-10 GUI tool-turn | **PASS** (`gui_tool_turn.json`) |
| **종합** | **GO** |

## 10. PROMPT 02 handoff notes

PROMPT 02/03 구현은 **시작하지 않음**.

다음 에이전트에게:

1. **입력 가정** — Wave 1.3 코드는 uncommitted `main` 위에 있다. Baseline `1ab0452`. 커밋은 사용자 요청 후에만.
2. **건드리지 말 것** — sidecar 116/115·catalog process/patch 기대를 “맞추기 위해” 느슨하게 만들지 말 것.
3. **PROMPT 02 범위 추정** — catalog/스키마 정합·잔여 Hermes 표면 제거·또는 Wave2. 착수 전 PROMPT 02 원문을 읽을 것.
4. **검증 재실행 목록** — 위 §7 명령 + `wave13-ntu` 증거 JSON 유지.
5. **아카이브** — 사용자 “끝” 확인 후 `docs/code-review/completed/`로 `git mv` (archive-finished-reports).

## 11. 조치

1. 사용자에게 GO 보고 (본 문서).
2. 요청 시에만 `main` 커밋.
3. PROMPT 02는 별도 brief로만 착수.
