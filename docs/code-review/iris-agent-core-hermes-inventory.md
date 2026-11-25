# IRIS Hermes Dependency Inventory (ACO-P1)

| 항목 | 내용 |
|---|---|
| 문서 번호 | ACO-P1 |
| 작성일 | 2026-11-25 |
| 관련 | ACO Ownership · PIN `a382af23` · `vendor/iris-agent-runtime` |
| 대상 | Hermes 이름·경로·실의존 (Iris Agent) |
| 목적 | A–G 분류로 소유화·제거 범위 고정. Dead는 importer/callee 근거 없이 확정하지 않음 |

## 1. 결론

제품 말 턴은 **InternalSidecar only**다. `parse_engine_source`는 항상 `InternalSidecar`를 돌려고, `ensure_iris_agent_runtime(..., start_gateway=False)`가 기본이다. Agent Loop 본체는 설치 트리의 `run_agent.AIAgent`(A)이며, Iris는 `_sidecar_main` → `agent_entry`로만 붙는다(B). 설치·갱신은 여전히 Nous pin clone + soft overlay(C)에 의존한다. Gateway·iris-control MCP는 제품 기본 턴에 필수가 아니나 **importer가 남아** F 후보로만 둔다(삭제 금지).

| Class | 의미 | 건수 |
|---|---|---|
| A | Active Core (설치 트리 루프) | 3 |
| B | Active Product Integration | 7 |
| C | Installation / Recovery / Overlay / Pin | 10 |
| D | Migration / Compatibility | 4 |
| E | Useful Upstream Capability | 5 |
| F | Dead/Obsolete **후보** (importer 잔존) | 3 |
| G | Reference / Bench / License | 2 |
| **합계** | | **34** |

근거 방법: Python `import`/호출 Grep + 모듈 소스 확인. code-review-graph는 2026-09 스냅샷이라 보조만 사용. 문자열 검색만으로 Dead 판정하지 않음.

## 2. 구조

```text
Chat send
  → shared_engine() / Engine(InternalSidecar)     [B]
  → runtime Popen _sidecar_main.py                [B]
  → agent_entry → run_agent.AIAgent               [B→A]
  → SpeakTools (speak_capability + aliases)       [B]
  → UDP done/fail → UI land_db

설치/갱신 (제품 턴과 갈림)
  → iris_agent_install / iris_agent_update        [C]
  → vendor/iris-agent-runtime PIN + overlays      [C]
  → apply_iris_agent_baseline_overlays            [C]
  → sync_iris_control (skills/soul/memory)        [B/C→E]

옵션 분기 (기본 OFF)
  → start_gateway=True → iris_agent_gateway :8642 [F후보]
```

## 3. 분류 정의

| Class | 용도 | 판단 |
|---|---|---|
| A | 설치 트리 Agent Loop·provider·tool parse | 컷오버 전까지 Reference Engine. P2 bake 대상 |
| B | Iris가 매 턴 타는 제품 경로 | 유지. InternalSidecar 계약 |
| C | pin·clone·overlay·update | P2 bake 후 soft-dep 축소. 즉시 삭제 금지 |
| D | hermes-agent 폴더·CLI shim·레거시 홈 | 마이그레이션 후 제거 가능. 호출자 이동 선행 |
| E | skills/soul/memory/plugins 소스 | Wave에서 ABSORB. 제품 동기화 있으면 KEEP |
| F | 기본 경로 미사용·tombstone | importer 0 확인 후에만 삭제 |
| G | bench·NOTICE·참조 스크립트 | REFERENCE. 제품 핫패스 아님 |

## 4. Inventory (요소별)

각 행: **호출자** = importer/callee 근거. **실행** = 제품 핫패스·설치 경로·자검만 구분. **제거 위험** = 지금 지우면 깨지는 범위.

### A — Active Core (3)

| 요소 | 호출자 | depends-on | 실행 | 제거 위험 | 권장 |
|---|---|---|---|---|---|
| 설치 트리 `run_agent.AIAgent` | `_sidecar_main._import_agent_class` → `agent_entry` (`from run_agent import AIAgent`) | 설치 checkout venv + pin SHA | 예 (매 말 턴) | 치명 | P2 동결 → owned 진입. 삭제 금지 |
| providers / tool calling / context (설치 트리 내부) | `AIAgent` 내부 (checkout) | ollama/API, toolsets, overlays | 예 | 치명 | KEEP until bake |
| `hermes_cli` / `iris_agent_cli` probe | `iris/engine/_home.py` `_PROBE_IMPORT` dual-accept | checkout 패키지 | 예 (ensure_ready probe) | 높음 | P3에서 owned CLI. dual-accept 유지 |

### B — Active Product Integration (7)

| 요소 | 호출자 | depends-on | 실행 | 제거 위험 | 권장 |
|---|---|---|---|---|---|
| `iris/engine/agent_entry.py` | `_sidecar_main._load_local_helper("agent_entry")` 또는 `IRIS_ENGINE_AGENT_MODULE` | `run_agent.AIAgent` | 예 | 높음 | P3 owned re-export. 경계 유지 |
| `iris/engine/_sidecar_main.py` | `runtime.py` `_SIDECAR_MAIN` Popen; 다수 `_check_*` / tests | agent_entry, SpeakTools wire, NDJSON | 예 | 치명 | 유지. Gateway 바인딩 없음 |
| `iris/engine/runtime.py` | `shared_engine` ← `iris_agent_workers` / extension worker / main | InternalSidecar, `_sidecar_main`, install_into, ollama_guard | 예 | 치명 | 유지 |
| `iris/engine/types.py` `InternalSidecar` | `parse_engine_source` → 항상 sidecar; EngineSource alias | `iris_agent_home()` | 예 | 치명 | 제품 계약. Gateway union 복원 금지 |
| `iris/infrastructure/agent_runtime.py` (home·supervisor) | install/gateway/setup/`ensure_iris_agent_runtime` | PIN, overlays, soul sync | 예 | 높음 | home/pin은 C와 공유. supervisor 유지 |
| `iris/infrastructure/speak_capability.py` | `main_window.set_speak_surface`, control_bindings, 다수 `_check_*` | absorbed aliases, Control Surface | 예 | 치명 | KEEP. SpeakTools 권위 |
| `iris/infrastructure/absorbed_tool_aliases.py` | `speak_capability`, `_check_absorbed_*`, tool contract checks | SpeakAllowlist | 예 | 높음 | KEEP |

### C — Installation / Recovery / Overlay / Pin (10)

| 요소 | 호출자 | depends-on | 실행 | 제거 위험 | 권장 |
|---|---|---|---|---|---|
| `iris/system/iris_agent_install.py` | `setup_protocol` install step, `runtime.install_into`, update/retire | git clone UPSTREAM@PIN, uv sync, baseline overlays | 예 (설치·복구) | 높음 | P5: vendor 설치로 교체. Nous clone 제거는 그 후 |
| `iris/system/iris_agent_update.py` | `IrisAgentUpdate*Worker` ← main_window | PIN, overlays, gateway helpers | 예 (UI 갱신) | 중 | vendor sync로 전환 |
| `vendor/iris-agent-runtime` (PIN/UPSTREAM/overlays) | `agent_runtime.load_pinned_sha`, tool_choice/absorbed snippet 경로 | 없음 (기준 권위) | 예 (설치 시) | 중 | P2 bake 후 즉시 삭제 금지. pin 계약 유지 |
| `iris_agent_ollama_guard.py` | `apply_iris_agent_baseline_overlays`; `runtime.py`; gateway health | checkout `run_agent` 패턴 | 설치시 + ensure | 중 | P2 bake |
| `iris_agent_tool_choice.py` | baseline overlays; `sync_iris_control`; `ai_hub_dialog` | vendor overlay + config | 설치·sync·설정 | 중 | P2 bake |
| `iris_agent_package_identity.py` | baseline overlays | checkout pyproject/entry | 설치시 | 중 | P2 bake into owned pyproject |
| `iris_agent_cli_rename_overlay.py` | baseline overlays; `_check_iris_agent_cli_rename` | checkout CLI 패키지명 | 설치시 | 중 | P2 bake; D shim과 짝 |
| `iris_agent_absorbed_toolsets.py` | **제품 baseline에 미연결** (아래 코드 리뷰). importer = `_check_iris_agent_absorbed_toolsets` + phase4 assert 기대 | vendor snippet → `toolsets.py` | 자검만 (현행) | 중 | P2 bake에 포함하거나 baseline 호출 복구. 삭제 금지 |
| `iris_agent_control_sync.py` (install-time sync 축) | setup_protocol, `iris_agent_workers`, apps/mcp_resource, 다수 state helpers | skills/soul/memory, mcp scrub | 예 | 중 | SpeakTools 자세 유지. Gateway 재기동 문구만 정리 |
| dead-check patch (`ensure_iris_agent_stdio_dead_check_patch`) | baseline overlays; sync | checkout stdio | 설치·sync | 중 | P2 bake |

### D — Migration / Compatibility (4)

| 요소 | 호출자 | depends-on | 실행 | 제거 위험 | 권장 |
|---|---|---|---|---|---|
| checkout 폴더 `hermes-agent` 폴백 | `iris_agent_repo_dir` (iris-agent 우선, 없으면 hermes-agent); install live/staging 경로 | 레거시 설치 | 예 (구 홈) | 중 | P5 후 iris-agent만. 컷오버 전 Reference 보존 |
| `iris_agent_cli_shim_overlay.py` | baseline overlays (F3 rename 후 no-op) | rename overlay | 설치시 | 낮음 | bake 후 제거 가능 |
| `legacy_agent_home` (`%LOCALAPPDATA%\hermes`) | `migrate_legacy_agent_home` / ensure home | 구 Hermes 데이터 | 마이그레이션만 | 낮음 | 활성 writer 금지 유지 |
| `scripts/apply_env_to_hermes.ps1` | **제품 import 없음**. `tests/test_iris_agent_env_example`가 env 문서에 스크립트명 없음을 assert | 레거시 LOCALAPPDATA hermes `.env` | 수동·드묾 | 낮음 | 문서 대체 후 보관/삭제 후보 |

### E — Useful Upstream Capability (5)

| 요소 | 호출자 | depends-on | 실행 | 제거 위험 | 권장 |
|---|---|---|---|---|---|
| `integrations/hermes-skills/iris-control/**` | `iris_agent_control_sync.ensure_skills_installed` (src_root) | sync → `~/.iris-light/agent/skills` | 예 (sync 시 복사) | 중 | KEEP. Wave ABSORB. 삭제 금지 |
| `integrations/hermes-soul/SOUL.md` | `iris_agent_soul_sync` ← ensure_runtime / sync / main_window persona | sync 원본 | 예 | 중 | KEEP |
| `iris_agent_soul_sync.py` | `ensure_iris_agent_runtime`, `sync_iris_control`, main_window | hermes-soul | 예 | 중 | KEEP |
| `iris_agent_memory_nudge.py` | `sync_iris_control.ensure_memory_nudge` | agent home MEMORY | 예 (sync) | 중 | KEEP. MCP 가르침 금지 계약 유지 |
| `integrations/hermes-plugins/web/serpapi` | **iris Python importer 없음** (제품 검색은 `iris_web` serpapi 백엔드) | 문서·소스 보관 | 제품 핫패스 아님 | 중 | IRIS web과 중복 검토. 소스 삭제 전 배포 경로 확인 |

### F — Dead / Obsolete 후보 (3) — 삭제 금지

| 요소 | 호출자 (잔존) | depends-on | 실행 | 제거 위험 | 권장 |
|---|---|---|---|---|---|
| `iris/system/iris_agent_gateway.py` | `ensure_iris_agent_runtime` (start_gateway=True일 때만 spawn); setup_protocol probe; install; update; main_window diagnosis; 다수 tests/`_check_*` | checkout executable, provider config | **부분** (제품 기본 spawn 없음) | 중 | P6 유틸 분리. `start_gateway` 기본 False 유지. importer 정리 전 삭제 금지 |
| `iris/mcp/iris_control_stdio.py` (+ `iris/mcp/__init__.py`) | sync scrub 검증, `_check_product_no_iris_control_mcp`, tool registry checks, hermes-mcp entry import | Control HTTP (과거) | tombstone: `TOOLS=[]`, `main()`→rc 2 | 중 | Speak 경로 아님 확정. 모듈은 자검·스크럽 증거가 참조 → P6 후 축소 |
| `integrations/hermes-mcp/iris_control_stdio_entry.py` | sync가 `~/.iris-light/hermes-mcp`에 동등 entry 생성; 레포 entry는 템플릿 | `iris.mcp.iris_control_stdio.main` | 호출 시 tombstone rc 2 | 중 | iris-control은 config에서 scrub. Emulator/mobile MCP와 분리해 보존 범위 확정 |

근거 (F를 Dead로 확정하지 않는 이유):
- Gateway: `_check_product_ready_no_gateway` / `_check_iris_agent_supervisor_phase4b`가 `start_gateway` 기본 False·제품 step에 spawn 없음을 잠그지만, 모듈 import·진단·opt-in 호출자가 존재한다.
- MCP: `ensure_mcp_in_config`가 `mcp_servers.iris-control`을 **항상 scrub**. 그러나 stdio 모듈·entry·자검이 살아 있다.

### G — Reference / Bench (2)

| 요소 | 호출자 | depends-on | 실행 | 제거 위험 | 권장 |
|---|---|---|---|---|---|
| `scripts/iris_hermes_bench/**` | 수동 / U00 baseline `_check_product_effect` (cwd=bench) | 로컬 tmp 산출물 | 비제품 (오프라인 grader) | 없음 | REFERENCE. P7 parity에 재사용 |
| Hermes MIT / THIRD_PARTY / PIN provenance | 배포·LICENSE.md §3 | vendor PIN | — | — | 보존. P2 Provenance Manifest |

## 5. 코드 리뷰 (갈림·빈 자리)

| 지점 | 이번 증상/역할 | 요청을 막지 못한/빈 자리 |
|---|---|---|
| `parse_engine_source` | 제품 소스를 InternalSidecar로 고정 | Gateway 잔여는 진단·opt-in만 |
| `ensure_iris_agent_runtime(..., start_gateway=False)` | 기본 gateway 미기동 | `start_gateway=True` 호출자·대형 gateway 모듈은 남음 |
| `apply_iris_agent_baseline_overlays` | ollama/tool_choice/identity/cli overlays | **`apply_absorbed_toolsets_overlay` 미호출**. `_check_iris_agent_home_phase4`는 포함을 assert → 계약 드리프트 |
| `sync_iris_control` | skills/soul/memory + iris-control scrub | hermes-plugins 복사 경로 없음 |
| `iris_control_stdio` | tombstone | hermes-mcp entry·state dir entry는 여전히 생성 가능 |

하지 않은 일: 설치 트리 내부 전 파일 목록화, 라이브 턴 재측정(P0), `vendor/iris-agent-core` 컷오버(P2+).

## 6. 개선안

| 빈 자리 | 조치 |
|---|---|
| absorbed_toolsets baseline 미연결 | P2 bake에 포함하거나 baseline 호출 복구. phase4 assert와 일치 |
| Gateway 모듈 거대·opt-in | P6: probe/진단 유틸만 남기고 spawn 경로 격리 |
| MCP tombstone + entry 잔존 | scrub 자검 유지한 채 entry 생성 축소 |
| Nous clone 설치 | P5: vendor/iris-agent-core 설치로 교체 |
| hermes-plugins 미동기화 | 제품 검색(`iris_web`)과 역할 정리 후 보관/흡수 결정 |

## 7. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| NousResearch/hermes-agent @ PIN | Agent Loop·providers·tool parse | 이미 pin. 전체 재작성 대신 bake |
| 기존 Iris overlays | ollama guard, tool_choice, identity, CLI rename/shim, absorbed toolsets | P2에서 소스 bake. 런타임 문자열 패치 축소 |
| SpeakTools / Control Surface | 도구 실행 권위 | 이미 제품 경로. MCP로 되돌리지 않음 |
| 찾지 못함 | Gateway 없는 동등 진단 전용 소형 라이브러리 | 현 gateway.py 분리로 충분 |

## 8. 조치

1. 이 문서를 ACO-P2 bake 범위의 입력으로 쓴다.
2. Dead 확정·삭제는 F 후보 importer 표가 0이 된 뒤(P6).
3. absorbed_toolsets 드리프트를 P2에서 닫는다.
4. 계획 파일은 수정하지 않는다. 커밋은 사용자 요청 시.
