# Iris Agent 툴 registry (Phase 2.2)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-TOOL-REG-P22 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Hermes기반-구현경로.md` §4 2단계 A, §10.1, Phase 2.1 |
| 대상 | 첫 실제 도메인 툴(`iris.wiki.list_notes`) native 이전 |
| 목적 | §10.1 툴 registry 게이트를 “실동작 1툴 소유”까지 전진 |

## 1. 결론

Phase 2.2는 **plan B가 아니다.**  
`iris.wiki.list_notes` 는 `IrisWiki.list_notes()` 를 제품 레지스트리에서 **in-process** 로 호출한다.  
문서화된 진입점은 `invoke_agent_tool`. MCP stdio → `:8765` 가 필요하면 자검이 실패한다.  
제품 채팅 전체의 MCP 제거는 **아직 아님** (루프 미연결·나머지 bridge 유지).

## 2. 구조

```
말 턴 / 에이전트 루프 (목표 진입점)
  └─ invoke_agent_tool(name, args)
         └─ IrisAgentToolRegistry.invoke
                ├─ native: iris.tools.ping | catalog | iris.wiki.list_notes
                │      └─ IrisWiki (디스크) — MCP/:8765 없음
                └─ mcp_bridge: iris.wiki.search 등 (아직 거부; 임시 MCP 경로)

클릭 / Control Surface
  └─ wiki.list_notes (기존 control_actions) — 에이전트 턴 없음 (유지)
```

이번 요청 분기: **list_notes native + 스킬 문구 + 자검**. 설정 UI·홈·채팅 워커 이름 변경 없음.

## 3. 코드 리뷰

| 지점 | 이번 일 | 막지 못한 것 |
|---|---|---|
| `agent_tool_registry.py` | `iris.wiki.list_notes` 핸들러·`invoke_agent_tool` | Hermes 루프에 미연결 |
| `IrisWiki.list_notes` | 실행 본체 재사용 | UI 새로고침(사이드바) 없음 — 목록 읽기만 |
| `control_actions/wiki.py` | 손대지 않음 | HTTP 제품 경로 유지 |
| MCP stdio | 손대지 않음 | 말 턴 전체 왕복 유지 |
| `iris-wiki/SKILL.md` | MCP Prefer·Hermes·mcp__ 제거 | 다른 iris-control 스킬 |

하지 않은 일: Phase 3 설정 필드 삭제, Phase 4 홈 이전, 새 `hermes_*` 모듈, MCP rename.

## 4. §10.1 (Phase 2.2 후)

| 게이트 | 상태 |
|---|---|
| 툴 registry 포크/제품 소유 | **부분 전진** — 실도메인 1툴(`list_notes`) native 소유. 루프 연결·MCP 제품경로 제거는 2.3+ |
| 설정 생성권 Iris | 열림 (3) |
| 대화 정본 하나 | 열림 (2·4) |
| supervisor 하나 | 열림 (3) |

## 5. 개선안 (빈자리)

1. 에이전트 루프가 `invoke_agent_tool` 을 1급으로 호출 (채팅 경로 관측).
2. `wiki.search` / mail / calendar / ide 를 native 또는 IPC 로 이전 후 MCP 제품 경로 축소.
3. 나머지 iris-control 스킬의 `mcp__` / 사용자 Hermes = 0.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Control `wiki.list_notes` | 노트 dict·paging 형태 | UI 창 의존 제거. IrisWiki 직접 |
| Hermes tool registry | 루프 schema 등록 | pin 트리 미 vendor. 제품 훅 먼저 |
| MCP tool 규약 | n/a | B안 금지 |

## 7. 검증

```powershell
.venv\Scripts\python.exe -m iris.system._check_iris_agent_runtime_phase1
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2_2
.venv\Scripts\python.exe -m iris.infrastructure.agent_tool_registry
```

## 8. 조치

1. Phase 2.3: 에이전트 루프(또는 chat worker)가 `invoke_agent_tool` 을 쓰는지 관측 가능하게 연결. 또는 다음 도메인 툴 1개 추가 native.
2. Phase 3: 설정 Hermes URL/Key/명령 **삭제** (숨김 금지) — 2단계 A 게이트가 “제품 경로에서 MCP 왕복 없음”에 더 가까워진 뒤.
