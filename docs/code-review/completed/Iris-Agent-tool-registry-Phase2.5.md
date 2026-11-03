# Iris Agent 툴 registry (Phase 2.5) — §10.1 gate 1 CLOSED

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-TOOL-REG-P25 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Hermes기반-구현경로.md` §4 2단계 A, §10.1 #1, Phase 2.4 |
| 대상 | seed 카탈로그 전원 native + speak/MCP redirect (제품 경로) |
| 목적 | gate 1 CLOSED — 제품 경로 = IrisAgentToolRegistry native |

## 1. 결론

Phase 2.5는 **plan B가 아니다.**  
`_SEED` 의 `mcp_bridge` 행을 **0**으로 줄였고, 남은 시드(mail·calendar·session·ide·project)에 in-process native 핸들러를 붙였다.  
speak(`HermesChatWorker` / `speak_invoke_agent_tool`)와 MCP `iris_invoke` 의 seed `control_action` 은 `:8765` 를 열지 않는다.  
Qt가 필요한 ide/project/get_state 는 Iris 프로세스에서 ControlSurface in-process 호출을 시도하고, MCP 자식·헤드리스에서는 `{ok:false, error:"requires_iris_ui", call_path:"native"}` 를 돌려 **HTTP로 우회하지 않는다**.  
**147개 Control MCP 전체 삭제를 주장하지 않는다.** 비-시드 `iris_invoke` → `:8765` 는 **compat only**.

## 2. 구조

```
말 턴
  └─ HermesChatWorker.run
         ├─ _wire_native_speak_tools
         │      ├─ iris.wiki.list_notes / iris.wiki.search
         │      ├─ iris.mail.list_accounts      ← disk
         │      └─ iris.calendar.list_events   ← disk
         │             └─ speak_invoke_agent_tool → native (MCP/HTTP 없음)
         └─ HermesClient.stream_chat (:8642)
                └─ [compat] 비-시드 툴만 Hermes MCP → :8765 가능

Hermes MCP iris_invoke (자식 프로세스)
  └─ iris_control_stdio._handle_tool
         ├─ try_native_control_invoke(seed control_action)
         │      └─ invoke_agent_tool native  ← :8765 없음
         │           ide/get_state/project → requires_iris_ui (Qt 없음)
         └─ else _http POST /v1/invoke → :8765  (비-시드 compat)

클릭 / Control Surface
  └─ control_actions — 에이전트 턴 없음 (유지)
```

이번 요청 분기: **seed 전원 native + MCP redirect + 자검 Phase 2.5**. Plan B rename-only MCP 금지. Phase 5 in-process 병합 없음.

## 3. 코드 리뷰

| 지점 | 이번 일 | 막지 못한 것 / 하지 않은 일 |
|---|---|---|
| `agent_tool_registry.py` | seed 전부 native; mail/calendar disk; Qt 바인딩은 live ControlSurface 또는 `requires_iris_ui` | 비-시드 147 액션 네이티브화 |
| `iris_control_stdio.py` | 기존 `try_native_control_invoke` 가 새 seed 도 커버 | `iris_get_state` MCP 툴명은 여전히 GET `/v1/state` compat |
| `hermes_workers.py` | wire에 mail+calendar 추가 (ide open 제외) | stream 중 Hermes가 비-시드 MCP를 부를 수 있음 |
| `hermes_memory_nudge.py` | v28 native seed 우선 문구 | write/run 등 비-시드는 여전히 mcp__ |
| skills email/calendar/session/work-start | native 이름·requires_iris_ui | vibe-code write/run 은 아직 mcp__ |
| Control `email.list_accounts` 등 | 손대지 않음 | 클릭 경로 유지 |

하지 않은 일: Phase 5 병합, fruit-fly, 새 `hermes_*` 모듈, 147 MCP 서버 삭제, git commit.

## 4. 개선안

구조상 빈 자리만:

1. 비-시드 Control 액션의 제품 경로 축소(필요 시 후속 phase) — 이번 gate 1 범위 밖.
2. Hermes 런타임이 native 툴 schema를 직접 노출하면 speak wire 외 호출도 강화 가능.
3. `iris_get_state` MCP 단축 툴 → native redirect(선택).

## 5. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Control `email.list_accounts` / `calendar.list_events` | 결과 필드 형태 | UI window 의존 제거·storage 직접 |
| `call_registered` + MainWindow `_control_surface` | ide/get_state/project in-process | MCP HTTP 재도입 금지 |
| Hermes tool registry 루프 | schema 노출 | pin 미 vendor; 제품 훅·리다이렉트 우선 |

## 6. 검증

```powershell
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2_5
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2_4
.venv\Scripts\python.exe -m iris.infrastructure.agent_tool_registry
```

## 7. 조치

1. §10.1 gate 1 → **CLOSED** (제품 경로 = native seed; `:8765` = compat only).
2. gate 2·3·4 이미 CLOSED → **일체화 완료** 선언 가능(§11 기준; Phase 5 선택).
3. 다음 단위는 비-시드 축소나 Phase 5 prove만 (요청 시).
