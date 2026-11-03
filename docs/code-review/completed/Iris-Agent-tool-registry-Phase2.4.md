# Iris Agent 툴 registry (Phase 2.4)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-TOOL-REG-P24 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Hermes기반-구현경로.md` §4 2단계 A, §10.1, Phase 2.3 |
| 대상 | `iris.wiki.search` native + covered wiki MCP 제품 경로 축소 |
| 목적 | speak/native·MCP `iris_invoke` 가 wiki list/search 에서 `:8765` 를 안 탐 |

## 1. 결론

Phase 2.4는 **plan B가 아니다.**  
`iris.wiki.search` 를 registry native 로 올렸고, speak 워커·스킬·넛지가 그 이름을 쓴다.  
Hermes 자식이 여전히 MCP `iris_invoke(action=wiki.list_notes|wiki.search)` 를 호출해도  
`try_native_control_invoke` 가 in-process 로 리다이렉트해 `:8765` 를 열지 않는다.  
**147개 Control 전체 MCP 제거는 아니다.** mail·ide·calendar 등은 `mcp_bridge` 잔여.

## 2. 구조

```
말 턴
  └─ HermesChatWorker.run
         ├─ _wire_native_speak_tools
         │      ├─ invoke_native_tool(iris.wiki.list_notes)  ← 2.3
         │      └─ invoke_native_tool(iris.wiki.search)     ← 2.4
         │             └─ speak_invoke_agent_tool → IrisWiki/DB (디스크)
         └─ HermesClient.stream_chat (:8642)
                └─ [임시] 기타 툴은 Hermes MCP → :8765 가능

Hermes MCP iris_invoke (자식 프로세스)
  └─ iris_control_stdio._handle_tool
         ├─ try_native_control_invoke(wiki.list_notes|wiki.search)
         │      └─ invoke_agent_tool native  ← :8765 없음 (2.4 축소)
         └─ else _http POST /v1/invoke → :8765  (나머지 액션)

클릭 / Control Surface
  └─ wiki.* control_actions — 에이전트 턴 없음 (유지)
```

이번 요청 분기: **search native + MCP 리다이렉트 + 자검**. Phase 3 설정 삭제 없음.

## 3. 코드 리뷰

| 지점 | 이번 일 | 막지 못한 것 |
|---|---|---|
| `agent_tool_registry.py` | search 핸들러·alias·`try_native_control_invoke` | embedder 없는 키워드 검색(Control UI 임베딩과 차이) |
| `iris_control_stdio.py` | wiki list/search 네이티브 리다이렉트 | 나머지 iris_invoke → :8765 |
| `hermes_workers.py` | wire에 search 포함 | stream 중 기타 MCP tool-call |
| `hermes_memory_nudge.py` | v27 wiki native 문구 | 다른 액션의 mcp__ 유도 |
| `iris-wiki/SKILL.md` | list+search native | write/import 는 아직 control |
| Control `wiki.search` | 손대지 않음 | 클릭 경로·임베딩 검색 유지 |

하지 않은 일: Phase 3 설정 Hermes URL/Key/명령 삭제, Phase 4 마이그레이션, 새 `hermes_*` 모듈, MCP 서버 rename, fruit-fly, git commit.

## 4. §10.1 (Phase 2.4 후)

| 게이트 | 상태 |
|---|---|
| 툴 registry 포크/제품 소유 | **부분 전진** — wiki list+search native + MCP 리다이렉트. 전 도메인 MCP 제품경로 제거는 미완 |
| 설정 생성권 Iris | 열림 (3) |
| 대화 정본 하나 | 열림 (2·4) |
| supervisor 하나 | 열림 (3) |

## 5. 개선안 (빈자리)

1. mail / calendar / ide 를 native 또는 IPC 로 이전 후 MCP 리다이렉트 확대.
2. 검색에 Control과 같은 embedder 옵션을 제품 설정에서 주입(선택).
3. Phase 3: 설정 UI Hermes URL/Key/명령 **삭제**.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Control `wiki.search` | hits/code_hits 결과 형태 | UI window·Ollama embedder 의존 제거 |
| `search_notes` / `search_code_notes` | in-process 검색 본체 | MCP rename 금지 |
| Hermes tool registry | 루프 schema | pin 미 vendor. 제품 훅·리다이렉트 우선 |

## 7. 검증

```powershell
.venv\Scripts\python.exe -m iris.system._check_iris_agent_runtime_phase1
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2_2
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2_3
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2_4
.venv\Scripts\python.exe -m iris.infrastructure.agent_tool_registry
```

## 8. 조치

1. **다음 단위 = Phase 3** (설정 Hermes URL/Key/명령 코드 삭제). 2.4에서 wiki MCP 왕복이 관측 가능하게 줄었으므로 착수 가능.
2. 전 도메인 MCP 제거·§10.1 완전 통과는 3·4와 추가 native 이전이 더 필요.
