# IRIS Wave 1.1 — Integration & Security Hardening Plan

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-25-AGENT-RUNTIME-W1.1 |
| 작성일 | 2026-11-25 |
| 기준 HEAD | `bdc6a557fd1ea4dce046bdc60ecbf03b4910c433` |
| 관련 | Wave 1 U00–U06 착지, [wave2-brief](iris-agent-unified-runtime-wave2-brief.md), [wave3-brief](iris-agent-unified-runtime-wave3-brief.md), [baseline](iris-agent-unified-runtime-baseline.md) |
| 대상 | Execution Runtime 실통합 · Process 보안 · Tool Contract · Env 보안 · WorkspaceEnv · Patch · Runtime 안정성 · 라이브 모델 게이트 |
| 목적 | Wave 2(U07–U11) 착수 전 P0 구조 결함을 검증 가능한 단위로 고친다. 이 문서는 **계획**이다. 구현은 운영자 go 이후. |
| 커밋/푸시 | 사용자 요청 전까지 금지 |
| 구현 상태 | 2026-11-25 — W11-A…H 완료 (control_invoke 10/10 after S10 retry; agent_turn/U00 잔여) |

## 1. 무엇이 바뀌는가

Wave 1이 남긴 `ExecutionRuntime` / `WorkspaceEnvironmentResolver` / `file_patch` / Speak SSOT는 **모듈로는 존재**하나, 제품 핫패스(`project.run` 12초 `wait_for_run_log`, `os.environ.copy()`, EMPTY_OBJECT 기본 스키마 101/116, process.start 권한 미검사, Theia buffer 미연동)가 그대로다. Wave 1.1은 이 경로를 **공통 런타임·정책·계약**에 붙이고, 격리 테스트 워크스페이스 + 실제 에이전트 턴으로 게이트한다.

## 2. 감사 스냅샷 (측정)

출처: 메인 직접 측정 + [Wave1 gap audit](b0f71c49-f681-4287-8f1c-014344f49ab3) 교차 확인.

| 사실 | 값 | 증거 |
|---|---|---|
| HEAD | `bdc6a55` Wave 1 land | `git rev-parse HEAD` |
| Runtime 제품 호출자 | `control_actions/process.py`만 | Grep `default_runtime` / `ExecutionRuntime` |
| `project.run` / IDE `terminal` | Theia bridge + `wait_for_run_log(..., min(timeout, 12.0))` | `project.py` ~453–524, ~484 |
| 로그 대기 방식 | 파일 **크기 안정(stable_sec)** 대기; 크기≠exit. exit는 `IRIS_EXIT` 줄만 | `project_ops.py` ~837–901 |
| Home `shell.run` / `terminal` | `iris_shell.stream_shell_job`; Runtime 미사용; 부모 env 전체 상속 | `shell.py` ~138–160 |
| `last_run.log` 래퍼 | `project_ops` tee 경로가 완료 권위; Runtime은 compat view만 | `project_ops.py` ~687–760; `execution_runtime.py` ~555–577 |
| Env 전달 | Runtime `os.environ.copy()`; shell 경로 env= 미지정 | `execution_runtime.py:250`; `iris_shell` |
| ProcessRecord | `session_id` / `workspace_id` 없음; `default_runtime()` 전역 싱글톤 | `ProcessRecord`; `589–594` |
| process.start 정책 | `confirm_required=False`, cwd=디렉터리만; `shell.run`은 confirm/high/홈 제한 | `process.py` vs `shell.py` |
| Speak 스키마 | grants 116, explicit 15, empty_default 101 | 런타임 카운트 |
| surface 불일치 | home `terminal`은 `command` required; **ide_companion `terminal`은 EMPTY** | gap audit 측정 |
| ToolResult 배선 | Control `ok`/`error`/`data`만; duration_ms/error_code 등 미연결 | `speak_capability` `_from_control` |
| IrisToolContract 기본 | `parallel_safe=True`, `headless_supported=not surface` 무조건 | `iris_tool_contract_from_grant` |
| Patch | sha/mtime·계획단계 conflict 있음; atomic replace·multi-file rollback·Theia buffer 미완; write는 `newline="\n"`(CRLF 보존 요구와 대조 필요) | `file_patch.py` |
| WorkspaceEnv | project argv 경로만 Resolver; `process.manage`/`shell.run`/shell-string `plan_run` 미적용 | `workspace_env.py`; `project_ops` |
| U00 라이브 벤치 | 공란 | wave2-brief §2 |
| Wave 2/3 브리프 | 보존 | `docs/code-review/iris-agent-unified-runtime-wave{2,3}-brief.md` |

## 3. 도메인 형태 (구현 전 고정)

| 개념 | 형태 |
|---|---|
| Run | `run_id`, `status∈ProcessStatus`, `exit_code`, `session_id`, `workspace_id`, `owner`, `cwd`, `env_id`, `stdout_ref`, `stderr_ref`, `started_at`, `finished_at` |
| Env bundle | allowlist + secret denylist로 만든 `Mapping[str,str]`; 로그/모델 컨텍스트에 secret 값 금지 |
| Tool contract | SpeakGrant.parameters ↔ Action handler 인자 ↔ Output schema; EMPTY만 인자 0개 도구 |
| Patch txn | fingerprint 스냅샷 → apply → 재검증 → atomic replace; 실패 시 rollback 목록 |
| Result | 프로세스 상태 ≠ 작업 성공; `exit_code!=0` → failed; cancel/tree-kill 검증 필드 |

## 4. PR 착륙 순서 · 의존 그래프

```
trunk (bdc6a55)
  │
  ├─ W11-A  Env filter + secret policy          [독립]
  ├─ W11-B  Process security (session/ownership) [독립, A와 파일 겹침 → A 후 또는 직렬]
  │
  └─ W11-C  Wire project.run/shell.run/terminal → Runtime   [depends A,B]
        │
        ├─ W11-D  WorkspaceEnv 전경로 + allow_create 계약   [depends C; workspace_env 공유]
        ├─ W11-E  Tool contract 전수                       [독립 가능; speak_capability 공유 → C 후 권장]
        ├─ W11-F  Patch engine 완성                        [독립]
        └─ W11-G  Runtime 안정성 (exit/cancel/retention)   [depends C]
              │
              └─ W11-H  Live model integration gate        [depends A–G P0]
                    │
                    └─ (gate green) → Wave 2 U07…

공유 쓰기 직렬: `execution_runtime.py` (A→B→C→G), `project.py`/`project_ops.py` (C→D), `speak_capability.py` (E), `shell.py`/`execution_policy.py` (B↔C), `control_bindings.py` (등록).
독립 병렬: F는 A–C와 병렬 가능. env helper / ownership 필드 / patch atomic은 제한적 병렬.
```

**리뷰 게이트(머지 전 운영자 확인):** W11-C (IDE Run/Task 회귀), W11-H (라이브 10시나리오).

**P0 착수 우선(감사 권고와 정렬):** B 정책 우회 차단 → C Runtime 통합 → A env(이미 B 전에 두었으므로 A→B→C 유지; A는 B와 파일 충돌로 선행) → E 스키마 → D Resolver → F Patch → G 안정성 → H 게이트.

## 5. 단위별 계획

### W11-A — 실행 환경변수 필터

- [x] Depends on: 없음
- [x] Files: `run_env.py` (new), `execution_runtime.py`, `iris_shell.py`, `_check_run_env.py` (new)
- [x] Change: `build_child_env` allowlist+denylist. Runtime·shell Popen 적용.
- [x] Result: 자식에 제품 시크릿 미전달 (단위 검증).
- [x] Verify
  - [x] Unit: `_check_run_env` + `_check_execution_runtime` + `_check_iris_shell` — 메인 재검증 pass (2026-11-25)
  - [x] Live: 시나리오 8 (W11-H) — control_invoke PASS (`VAL=None`, 2026-11-25)
  - [x] Perf: n/a
- Residual: project.run/IDE bridge/sidecar env는 C·후속; COMSPEC/APPDATA 필요 시 allow_keys 확장

### W11-B — Process Security

- [x] Depends on: W11-A. **P0 정책 단위**
- [x] Files: `execution_policy.py`, `execution_runtime.py`, `control_actions/process.py`, `speak_capability.py`(schema 최소), checks
- [x] Change: start=high+human_confirm; cwd under workspace_root/home; session ACL; wait 300s cap; not sandbox.
- [x] Result: manage start가 shell 정책을 우회하지 않음 (단위).
- [x] Verify
  - [x] Unit: policy/runtime/run_env — 메인 재검증 pass (2026-11-25)
  - [x] Live: 시나리오 9 (W11-H) — control_invoke+unit_proxy PASS (confirm_required + cross-session deny)
  - [x] Perf: n/a
- Residual: 카탈로그 confirm_required=False(start만 동적); 직접 `start()`는 내부 신뢰 경로; project.run 미연결→C

### W11-C — Execution Runtime 실통합

- [x] Depends on: W11-A, W11-B
- [x] Files: `project.py`, `shell.py`, `project_ops.py` (`start_managed_run`/`wait_managed_run`), `iris_shell.py`, `_check_run_path_runtime_wire.py`
- [x] Change: Runtime start/wait 권위; IDE는 `echo IRIS_RUN_ID=` 시각화; 12s/log wait·일반 `upsert_iris_run_task` 제거.
- [x] Result: process_manage가 동일 run_id 조회 (단위).
- [x] Verify
  - [x] Unit: wire+runtime+policy+run_env+ide+bind+shell — 메인 재검증 pass (2026-11-25)
  - [x] Live: 시나리오 1–3 + IDE Run (W11-H) — control_invoke PASS (32s wait via Runtime, distinct stdout_ref)
  - [x] Perf: n/a
- Residual: IDE에 stdout 라이브 테일 없음(run_id echo만); `_check_project_run_status` 베이스 ImportError는 범위 밖

### W11-D — Workspace Environment 완성

- [x] Depends on: W11-C
- [x] Files: `workspace_env.py`, `project_ops.py`, `execution_runtime.py` (manage start bind), checks
- [x] Change: user → VIRTUAL_ENV/CONDA → .venv → uv/poetry(락+바이너리) → system; `bind_execution_argv`; hot path `allow_create=False`. shell-string 의도적 미개입.
- [x] Result: argv/python 경로 공통 Resolver (단위).
- [x] Verify
  - [x] Unit: workspace+bind+wire+runtime — 메인 재검증 pass (2026-11-25)
  - [x] Live: 시나리오 5 (W11-H) — control_invoke PASS (격리 `.venv` bind)
  - [x] Perf: n/a
- Residual: shell-string 미바인드; conda는 CONDA_PREFIX만; environment.yml alone 미지원

### W11-E — Tool Contract 전수

- [x] Depends on: W11-C 이후
- [x] Files: `speak_capability.py`, `_check_tool_contract.py`
- [x] Change: explicit 15→72; empty 101→44 (`EMPTY_SCHEMA_ACTIONS` 핀); project.run/IDE terminal required; conservative IrisToolContract; ToolResult duration_ms/error_code/call_id 배선.
- [x] Result: 고위험·인자 필요 도구 실스키마 (단위).
- [x] Verify
  - [x] Unit: tool_contract + absorbed_wire + baseline — 메인 재검증 pass (2026-11-25); schema chars home=29663 ide=29971 (보고만)
  - [x] Live: 시나리오 7 (W11-H) — control_invoke+unit_proxy PASS (`browser_navigate` required + live empty `project.run` fail)
  - [x] Perf: 향상 주장 없음 (U00 공란)
- Residual: 일부 required 느슨; schema version/output schema 미도입

### W11-F — Patch Engine 완성

- [x] Depends on: 없음 (C와 병렬 가능)
- [x] Files: `file_patch.py`, `patch_buffer_sync.py` (new stub), `_check_file_patch_engine.py`
- [x] Change: atomic `os.replace`; multi-file rollback; CRLF/encoding 보존; delete fingerprint; dirty/conflict 거부. Theia: 훅 스텁만 (`ide_refresh: stub`).
- [x] Result: 디스크 안전 적용 (단위). IDE 버퍼 실동기화는 훅 미등록 상태.
- [x] Verify
  - [x] Unit: `_check_file_patch_engine` — 메인 재검증 pass (2026-11-25)
  - [x] Live: 시나리오 6 (W11-H) — control_invoke PASS (disk match; `ide_refresh=stub`)
  - [x] Perf: n/a
- Residual: `project.py`에 훅 미연결; 실 Theia notify API 부재

### W11-G — Runtime 안정성

- [x] Depends on: W11-C
- [x] Files: `execution_runtime.py`, `project_ops.py`, `project.py`, `_check_execution_runtime.py`, `_check_run_path_runtime_wire.py`
- [x] Change: exit≠0 → FAILED; last_run latest-only; retention prune; tree kill Win/Unix; result ok=false on fail.
- [x] Result: 단위에서 실패/compat/retention 고정.
- [x] Verify
  - [x] Unit: P0 suite 메인 재검증 pass (2026-11-25) — runtime/wire/run_env/policy/patch/contract/workspace
  - [x] Live: 시나리오 3, 4 (W11-H) — control_invoke PASS (concurrent refs + cancel tree dead)
  - [x] Perf: n/a
- Residual: manage(wait) transport ok ≠ task success; Unix tree kill 미실측(이 PC는 Windows)

### W11-H — 실제 모델 통합 게이트 (완료 게이트)

- [x] Depends on: W11-A…G의 P0
- [x] Files: 격리 workspace + `.iris_light_test_tmp/verify-iris/wave11h-20261125-022556/evidence.json`; wave2-brief U07 Depends 한 줄 갱신
- [x] Change: 구현 추가 최소. **control_invoke / unit_proxy** (agent_turn 미사용 — 사용자 세션 오염 회피). U00=미측정.
- [x] Blocker: 구 Iris `process.manage` start HUD hang(>3s) → `iris_started_by_gate.pid`로 재기동 후 `process.py`(no HUD; auto/chat only; else `confirm_required`) 반영.
- [x] Scenarios (final `evidence.json` 2026-11-25)
  1. [x] terminal Python → process.manage status 동일 run_id — `control_invoke`
  2. [x] ≥30s Runtime wait (12s cut 없음) — `control_invoke`
  3. [x] 동시 2작업 stdout_ref 분리 — `control_invoke`
  4. [x] cancel + 자식 트리 종료 — `control_invoke`
  5. [x] 격리 `.venv` Resolver 일치 — `unit_proxy` (live IDE cwd miss 시 Resolver 단위)
  6. [x] apply_patch disk 일치 (`ide_refresh=stub`) — `control_invoke`
  7. [x] required args (`browser_navigate` empty reject + live url required) — `control_invoke+unit_proxy`
  8. [x] 비밀 env 누출 차단 — `control_invoke`
  9. [x] 무권한 start `confirm_required`(<3s, `_chat=None`) + 타 세션 거부 — `control_invoke+unit_proxy`
  10. [x] ping + project.run 생존 — `control_invoke` (중간 10054 후 Iris 재기동·재게이트 PASS)
- [x] Verify
  - [x] Unit: 선행 P0 checks green
  - [x] Live: `passed=10/10`, `wave2_gate=go` (agent_turn 아님)
  - [x] Perf: U00 **미측정**
- Wave2 gate: **go** (잔여: agent_turn 미증명, Theia buffer stub, 풀 GUI 육안, U00 공란)
- [x] process.manage start HUD 데드락 수정 (`process.py` non-HUD confirm) — 게이트 PID로 재시작 반영 완료

## 6. Wave 2/3 의존 갱신 (브리프 보존)

| 브리프 | 유지 | Wave 1.1 후 한 줄 |
|---|---|---|
| wave2 | U07–U11 본문 보존 | U07 Depends on: Wave 1.1 gate (W11-H) green; U05 경로는 Runtime-wired — **갱신 완료 (2026-11-25)** |
| wave3 | 보존 | Wave 1.1 P0 미완 시 착수 금지 명시만 |

## 7. 기존 검증 명령 (단위마다 재실행)

```powershell
.venv\Scripts\python.exe -m iris.system._check_execution_runtime
.venv\Scripts\python.exe -m iris.system._check_execution_policy
.venv\Scripts\python.exe -m iris.system._check_workspace_environment
.venv\Scripts\python.exe -m iris.system._check_file_patch_engine
.venv\Scripts\python.exe -m iris.infrastructure._check_tool_contract
.venv\Scripts\python.exe -m iris.infrastructure._check_unified_runtime_baseline
.venv\Scripts\python.exe -m iris.ui._check_ide_run_python
```

라이브는 격리 workspace + Iris 1 GUI + Agent ON. 사용자 데이터 경로 금지.

## 8. Throughput checkpoint (구현 go 시)

| 차원 | 내용 |
|---|---|
| Blocking first | W11-A → W11-B (공유 `execution_runtime.py`) |
| Independent | W11-F ∥ (A–B 동안); W11-E는 C 이후 권장 |
| Shared mutable | `execution_runtime.py`, `project.py`/`project_ops.py`, `speak_capability.py` — 동시 쓰기 금지 |
| Smallest decomposition | 단위=위 PR; 메인=설계·재검증, 코드=fresh poteto-agent/unit |

## 9. 미증명 / 리스크

- U00 라이브 벤치 수치: 아직 공란. Wave 1.1도 환경 없으면 “미측정”으로 남긴다.
- Theia buffer API 가용성: F에서 프로토타입으로 확인 후 범위 축소 가능.
- IDE Run UX: C는 시각화 유지가 계약. 깨지면 즉시 롤백 단위.

## 10. 조치

1. 운영자가 이 계획을 승인(go)하면 W11-A부터 TDD 단위로 구현한다.
2. 각 단위: 실패 체크 → 최소 구현 → 메인 재검증 → 변경 파일·명령·결과·미해결을 이 문서 또는 단위 로그에 기록.
3. W11-H green 전에 Wave 2 착수 금지.
4. commit/push는 사용자 요청 시에만.
