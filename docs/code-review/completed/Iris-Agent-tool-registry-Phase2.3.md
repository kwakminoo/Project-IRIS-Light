# Iris Agent 툴 registry (Phase 2.3)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-TOOL-REG-P23 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Hermes기반-구현경로.md` §4 2단계 A, §10.1, Phase 2.2 |
| 대상 | speak/chat 경로에 `invoke_agent_tool` 관측 가능 연결 |
| 목적 | HermesChatWorker가 native `iris.wiki.list_notes`를 MCP 없이 호출 |

## 1. 결론

Phase 2.3은 **plan B가 아니다.**  
`HermesChatWorker.run` → `_wire_native_speak_tools` → `invoke_native_tool` → `speak_invoke_agent_tool` → `invoke_agent_tool` 로  
`iris.wiki.list_notes` 를 **in-process** 호출한다. MCP stdio → `:8765` 가 필요하면 자검이 실패한다.

**남은 채팅 갭.** Hermes 자식 프로세스 루프가 모델 tool-call 을 여전히 MCP로 보낼 수 있다.  
Iris speak 워커는 native 경로를 소유·증명했지만, Hermes 내부 MCP 제품 경로 전면 제거는 Phase 2.4.

## 2. 구조

```
말 턴
  └─ HermesChatWorker.run
         ├─ _wire_native_speak_tools          ← Phase 2.3 (관측)
         │      └─ invoke_native_tool
         │             └─ speak_invoke_agent_tool
         │                    └─ invoke_agent_tool("iris.wiki.list_notes")
         │                           └─ IrisWiki (디스크) — MCP/:8765 없음
         └─ HermesClient.stream_chat (:8642)
                └─ [임시] Hermes MCP → :8765 (다른 툴·모델 tool-call)

클릭 / Control Surface
  └─ wiki.list_notes (control_actions) — 에이전트 턴 없음 (유지)
```

이번 요청 분기: **워커 speak 배선 + 자검**. 설정 UI·홈·워커 공개 이름 변경 없음.

## 3. 코드 리뷰

| 지점 | 이번 일 | 막지 못한 것 |
|---|---|---|
| `agent_tool_registry.py` | `speak_invoke_agent_tool`·alias | Hermes 프로세스 내부 루프 |
| `hermes_workers.py` | `invoke_native_tool`·`_wire_native_speak_tools` | stream 중 MCP tool-call |
| `IrisWiki.list_notes` | 재사용 | UI 사이드바 새로고침 |
| MCP stdio | 손대지 않음 | Hermes→:8765 제품 잔여 |
| `iris-wiki/SKILL.md` | speak 경로 문구 | 다른 iris-control 스킬 mcp__ |

하지 않은 일: Phase 3 설정 삭제, Phase 4 홈 이전, 새 `hermes_*` 모듈, MCP rename, fruit-fly.

## 4. §10.1 (Phase 2.3 후)

| 게이트 | 상태 |
|---|---|
| 툴 registry 포크/제품 소유 | **부분 전진** — speak 워커가 native list_notes 호출. Hermes MCP 제품경로 제거는 2.4 |
| 설정 생성권 Iris | 열림 (3) |
| 대화 정본 하나 | 열림 (2·4) |
| supervisor 하나 | 열림 (3) |

## 5. 개선안 (빈자리)

1. Hermes 루프/tool registry가 Iris native IPC(또는 동등)로 list_notes 등을 호출하게 바꿔 MCP 제품 경로 축소.
2. `wiki.search` / mail / calendar / ide native 또는 IPC 이전.
3. 나머지 iris-control 스킬 `mcp__` / 사용자 Hermes = 0.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Hermes tool registry | 루프 schema·호출 | pin 트리 미 vendor. 제품 훅 먼저 |
| Control `wiki.list_notes` | 클릭 경로 유지 | 에이전트 턴과 분리 계약 |
| MCP rename | n/a | B안 금지 |

## 7. 검증

```powershell
.venv\Scripts\python.exe -m iris.system._check_iris_agent_runtime_phase1
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2_2
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2_3
.venv\Scripts\python.exe -m iris.infrastructure.agent_tool_registry
```

## 8. 조치

1. Phase 2.4: 더 많은 도메인 툴 native + Hermes MCP 제품 경로 축소(관측).
2. Phase 3: 설정 Hermes URL/Key/명령 **삭제** — 2.4에서 MCP 왕복이 더 줄어든 뒤.
