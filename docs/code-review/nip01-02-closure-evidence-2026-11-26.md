# NIP-01 / NIP-02 Closure Evidence

| 항목 | 내용 |
|---|---|
| 문서 번호 | NIP01-02-CLOSE-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | Wave 1.6 · FIG-29 · phase23 · phase00 R-ASSETS-ABSORB |
| 대상 | Native Independence + Residual Absorption 잔여 검증 |
| 목적 | 제품 실행에 필요한 외부 Hermes 의존성만 재검증·최소 제거. 구현 반복·물리 삭제·migration 승격 금지 |
| HEAD | `029c1ceef289d78f7fb4a66271d686c95cd20aba` (+ 로컬 미커밋 최소 잔여 수정) |

## 1. 결론

제품 선택·설치·부팅·채팅 핫패스에서 Hermes auto-fallback·`:8642` spawn 필수 의존성은 **없다**. Live resolve는 Owned slot만 쓴다. `hermes-agent` 홈은 Reference로 남고 `selected_owned_engine`이 이름 단위로 건너뛴다. gateway 모듈은 진단·opt-in으로 **ISOLATE**. 이번 세션에서 제품 dataclass/supervisor 기본 명령 `"hermes"`와 inventory freeze를 깨던 `ExternalGateway` **주석 잔여**만 최소 수정했다. `legacy_migration_approved`·hermes 홈 삭제는 하지 않았다.

원칙: **Prove It Works** (포커스 `_check_*` 17종 exit 0 + live selection 실측), **Laziness Protocol** (제품 필수 잔여만 고침).

## 2. 확인한 사실

| 사실 | 출처 | 라벨 |
|---|---|---|
| Live active=`iris-agent.slot-272facc0f5fd4b6f`, previous=owned slot, `hermes-agent` 존재하나 resolve 제외 | `python -c` selection probe | measured |
| `selected_owned_engine`이 `LEGACY_AGENT_CHECKOUT_NAME` skip | `agent_runtime.py` | measured |
| `iris_agent_repo_dir` = selected ∨ `iris-agent/` (hermes recovery 분기 없음; phase23 문서보다 강함) | self-check + 소스 | measured |
| `start_gateway` 기본 False · product warm/setup/health에 spawn 없음 | 계약 체크 | measured |
| Native dispatcher가 Hermes `registry.dispatch` 차단 | `_check_native_tool_hermes_disabled` | measured |
| FIG-29 REMOVE 후보 없음 · gateway ISOLATE | 선행 감사 유지 | inferred |
| R-ASSETS-ABSORB Conversation Loop 전 분기 실행 증거 | phase00 tracker | OPEN / 제품 외부 checkout 필수는 아님 |

## 3. Subclaim PASS/FAIL

| # | Subclaim | 판정 | 증거 |
|---|---|---|---|
| 1 | Hermes auto-fallback 없음 (선택/설치 핫패스) | **PASS** | `selected_owned_engine` skip legacy; `iris_agent_repo_dir` → owned/`iris-agent`; `agent_runtime` self-check exit 0; live probe |
| 2 | Gateway spawn/connect 제품 호출자 0 | **PASS** | `_check_product_no_gateway_spawn` · `_check_product_ready_no_gateway` · `_check_gateway_retired_product_surface` · `_check_gateway_legacy_isolated` · `_check_iris_agent_supervisor_phase4b` · `_check_iris_agent_engine_setup_step` 전부 exit 0 |
| 3 | 외부 Hermes checkout/CLI가 제품 필수 아님 | **PASS** | product residue exit 0; owned install → `vendor/iris-agent-core`; live repo_dir=owned slot; `hermes.exe`는 executable 후보 말단만 (허용) |
| 4 | Recovery/diagnostic 격리 | **PASS** | `_check_hermes_gateway_diagnostics` exit 0 (모듈 유지); product surface에 `ensure_iris_agent_gateway_running` 없음; setup detect에 `is_iris_agent_gateway_running` 없음 |
| 5 | R-ASSETS-ABSORB / residual 표 재검 | **PASS (핫패스)** / **OPEN (흡수 완주)** | absorbed_toolsets 자검 exit 0 · FIG-29 ISOLATE 유지; Conversation Loop 전분기 증거는 phase00 OPEN (외부 Hermes 제품 의존 아님) |
| 6 | 잔여 제품 기본값 `"hermes"` / freeze 주석 | **PASS (수정 후)** | `BackendRoute.command`·`ensure_iris_agent_runtime(command=)` → `iris-agent`; settings/ollama_guard 주석에서 `ExternalGateway` 제거; inventory freeze · no_compat_aliases exit 0 |

## 4. 구조

```
제품 요청
  ├─ Settings.agent_* (command=iris-agent, base_url="")
  ├─ SetupProtocol / warm_services
  │    └─ ensure_iris_agent_runtime(..., start_gateway=False)  ← gateway skip
  ├─ Engine.ensure_ready → InternalSidecar
  │    └─ selected_owned_engine(home)
  │         active → iris-agent/ → previous
  │         ✗ name==hermes-agent 이면 continue
  │    └─ 없으면 canonical iris-agent/ (미존재 가능 → fail-closed)
  ├─ Sidecar chat
  │    └─ _install_iris_engine_tools → native dispatch
  │         registry.dispatch → TOOL_NOT_AVAILABLE (Hermes 원본 차단)
  └─ (opt-in only) iris_agent_gateway ensure/diagnose  ← ISOLATE
```

이번 요청이 갈라지는 지점: NORMAL resolve·ProductReady가 `:8642`/hermes-agent를 타는지. **타지 않음**.

## 5. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 요청을 막지 못한 이유 / 조치 |
|---|---|---|
| `selected_owned_engine` | legacy 이름 skip + integrity | 이미 구현됨 — 재검증만 |
| `iris_agent_repo_dir` | owned 없으면 canonical만 | phase23의 hermes recovery 분기는 현재 코드에 없음 (더 강함) |
| `ensure_iris_agent_runtime` | `start_gateway=False` | 유지. `command` 기본만 `iris-agent`로 맞춤 |
| product workers / setup / health | spawn 문자열 없음 | 계약 체크로 잠금 |
| `_sidecar_main` native install | Hermes registry 가드 | `_check_native_tool_hermes_disabled` |
| `BackendRoute.command` | 기본 `"hermes"` 잔여 | **수정** → `"iris-agent"` (collect_reply는 command 미사용이나 제품 표면 기본값) |
| settings / ollama_guard 주석 | `ExternalGateway` 토큰 | **수정** — inventory freeze 0 유지 |
| `iris_agent_gateway` | 진단·opt-in | ISOLATE — 삭제 안 함 |
| `~/.iris-light/agent/hermes-agent` | Reference 존재 | 삭제 금지 (KEEP) |

하지 않은 일: hermes 홈 삭제, `legacy_migration_approved=true`, commit/push, vendor/integrations 물리 삭제, R-ASSETS-ABSORB Conversation Loop 전분기 라이브 매트릭스.

## 6. 개선안

| 빈 자리 | 내용 |
|---|---|
| R-ASSETS-ABSORB 실행 증거 | Conversation Loop 등 흡수 자산의 분기별 라이브 증거는 별 단위 (제품 외부 checkout 의존과 분리) |
| absorbed_toolsets baseline | FIG-29 ISOLATE — baseline overlay 미연결은 유지; 제품 핫패스 차단 아님 |
| phase23 문서 드리프트 | 문서의 hermes recovery 분기는 현재 `iris_agent_repo_dir`와 불일치 — 문서 갱신은 별 요청 |

## 7. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| 찾지 못함 | — | 잔여는 로컬 계약·기본값 정리로 충분. 외부 프레임워크 불필요 |

## 8. 이번 세션 최소 수정

| 파일 | 변경 |
|---|---|
| `iris/ui/workers/backend_call.py` | `BackendRoute.command` 기본 `iris-agent` + self-check |
| `iris/infrastructure/agent_runtime.py` | `ensure_iris_agent_runtime(command=)` 기본 `iris-agent` |
| `iris/config/settings.py` | 주석에서 `ExternalGateway` 제거 |
| `iris/system/iris_agent_ollama_guard.py` | 주석에서 `ExternalGateway` 제거 |
| `iris/system/_check_iris_agent_no_compat_aliases.py` | stale `_AGENT_BACKENDS` → `BACKEND_AGENT` / command 기본 assert |

## 9. 검증 명령 · exit codes

```powershell
.venv\Scripts\python.exe -m iris.ui.workers.backend_call                                    # 0
.venv\Scripts\python.exe -m iris.system._check_product_ready_no_gateway                     # 0
.venv\Scripts\python.exe -m iris.system._check_product_no_gateway_spawn                     # 0
.venv\Scripts\python.exe -m iris.system._check_gateway_retired_product_surface              # 0
.venv\Scripts\python.exe -m iris.system._check_gateway_legacy_isolated                      # 0
.venv\Scripts\python.exe -m iris.system._check_iris_agent_product_residue                   # 0
.venv\Scripts\python.exe -m iris.infrastructure._check_native_tool_hermes_disabled          # 0
.venv\Scripts\python.exe -m iris.system._check_iris_agent_supervisor_phase4b                # 0
.venv\Scripts\python.exe -m iris.system._check_iris_agent_engine_setup_step                 # 0
.venv\Scripts\python.exe -m iris.engine._check_iris_agent_sidecar_only                      # 0
.venv\Scripts\python.exe -m iris.infrastructure.agent_runtime                               # 0
.venv\Scripts\python.exe -m iris.system._check_iris_agent_owned_install                     # 0
.venv\Scripts\python.exe -m iris.system._check_iris_agent_absorbed_toolsets                 # 0
.venv\Scripts\python.exe -m iris.system._check_hermes_gateway_diagnostics                   # 0
.venv\Scripts\python.exe -m iris.ui.window._check_chat_title_route                          # 0
.venv\Scripts\python.exe -m iris.system._check_iris_agent_inventory_freeze                  # 0
.venv\Scripts\python.exe -m iris.system._check_iris_agent_no_compat_aliases                 # 0
```

**FAIL_COUNT=0** (재실행 후).

## 10. Residual 표 (FIG-29 재확인)

| 대상 | 분류 | 비고 |
|---|---|---|
| vendor tools registry / model_tools / toolsets | KEEP | dispatch만 가드 |
| `iris_agent_gateway.py` | ISOLATE | 진단·opt-in |
| `iris_agent_absorbed_toolsets` | ISOLATE | 자검 OK · baseline 미연결 |
| integrations hermes-* | KEEP/ISOLATE/REFERENCE | FIG-29 유지 |
| `~/.iris-light/agent/hermes-agent` | REFERENCE | 삭제 금지 · resolve skip |
| BackendRoute / runtime command 기본 | 제품 정본 | 이번 세션 `iris-agent`로 맞춤 |

## 11. 조치

1. NIP-01 핫패스·NIP-02 제품 spawn 잔여 검증은 이 문서로 닫는다 (모듈 ISOLATE·R-ASSETS-ABSORB 전분기 OPEN은 유지).
2. commit/push·`legacy_migration_approved`·hermes 물리 삭제는 요청 전까지 하지 않는다.
3. 다음 가역 단위(원하면): R-ASSETS-ABSORB 분기 증거, phase23 문서 동기화, NIP-12 회귀 묶음.
