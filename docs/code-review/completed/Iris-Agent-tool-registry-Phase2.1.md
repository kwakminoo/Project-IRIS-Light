# Iris Agent 툴 registry (Phase 2.1)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-TOOL-REG-P21 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Hermes기반-구현경로.md` §4 2단계 A, §10.1, §11 |
| 대상 | 제품 측 native tool registry 골격 + 1툴 dry-run |
| 목적 | §10.1 툴 registry 소유권 게이트를 관측 가능하게 전진 |

## 1. 결론

Phase 2.1은 **plan B(MCP 이름만 변경)가 아니다.**  
Iris 제품이 `iris/infrastructure/agent_tool_registry.py` 로 툴 카탈로그와 **native invoke** 를 소유한다.  
`iris.tools.ping` / `iris.tools.catalog` 는 MCP stdio → `:8765` 없이 동작한다.  
나머지 시드 항목은 당분간 `mcp_bridge` 로 표기한다. 제품 채팅 경로의 MCP 왕복 제거는 Phase 2.2.

## 2. 구조

```
말 턴 (아직 Hermes/gateway)
  ├─ [2.2 목표] IrisAgentToolRegistry.invoke(native)
  │      └─ iris.tools.ping / catalog  (제품 소유, in-process)
  └─ [임시] MCP iris-control stdio → Control Surface :8765
         └─ control_actions (실행 본체 유지)
```

이번 요청 분기: **registry + dry-run 자검** 만. UI/홈/MCP 제거 없음.

## 3. 코드 리뷰

| 지점 | 이번 일 | 막지 못한 것 |
|---|---|---|
| `agent_tool_registry.py` | 카탈로그·native 핸들러·bridge 거부 | 에이전트 루프 미연결 |
| `ActionRegistry` (control_surface) | 손대지 않음 | HTTP 제품 경로 유지 |
| MCP stdio | 손대지 않음 | 말 턴 왕복 유지 |
| SOUL.md | Hermes 부정문 삭제 | 런타임 홈 동기화는 기존 sync |
| iris-session-status / work-start | Hermes·mcp__ 접두 제거 | 다른 스킬·Live Activity 접두 |

하지 않은 일: 설정 UI 필드 삭제, 홈 마이그레이션, 새 `hermes_*` 모듈, MCP 서버 rename.

## 4. §10.1 (Phase 2.1 후)

| 게이트 | 상태 |
|---|---|
| 툴 registry 포크/제품 소유 | **부분 전진** — 제품 훅+native 2툴. 에이전트 루프 연결·MCP 제품경로 제거는 2.2 |
| 설정 생성권 Iris | 열림 (3) |
| 대화 정본 하나 | 열림 (2·4) |
| supervisor 하나 | 열림 (3) |

## 5. 개선안 (빈자리)

1. 에이전트 루프가 `IrisAgentToolRegistry.invoke` 를 1급으로 호출.
2. `mcp_bridge` 항목을 IPC/native 핸들러로 이전 후 MCP 제품 경로 제거.
3. 스킬 전부에 `mcp__iris_control__` / 사용자 `Hermes` = 0.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Hermes tool registry (upstream) | 루프가 툴 schema 를 읽는 방식 | pin 트리 미 vendor. 제품 훅 먼저 |
| MCP tool 규약 | schema 형태 참고 | B안 완료 처리 금지 |
| LangChain Tool | n/a | 찾지 못함(불필요). 기존 ActionRegistry 형태면 충분 |

## 7. 검증

```powershell
.venv\Scripts\python.exe -m iris.system._check_iris_agent_runtime_phase1
.venv\Scripts\python.exe -m iris.system._check_iris_agent_tool_registry_phase2
```

## 8. 조치

1. Phase 2.2: `iris.wiki.list_notes` native + `invoke_agent_tool` 자검 — 문서 `Iris-Agent-tool-registry-Phase2.2.md`.
2. Phase 3: 설정 Hermes URL/Key/명령 **삭제** (숨김 금지) — 2.3에서 루프 연결·MCP 축소 후.
