# IRIS Unified Agent Runtime — Wave 2 상세 브리프 (U07–U11)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-24-AGENT-RUNTIME-W2 |
| 작성일 | 2026-11-24 |
| 관련 | [iris-agent-unified-runtime-baseline.md](iris-agent-unified-runtime-baseline.md), Wave 1 U00–U06 |
| 대상 | U07 Agent Optimize · U08 Memory/Skills · U09 Orchestration · U10 Provider/MCP · U11 Extended Caps |
| 목적 | Wave 1 green 이후 구현 단위별 파일·계약·검증을 고정한다. 이 문서는 코드 완료 주장이 아니다. |

## 1. 결론

Wave 1이 Speak SSOT·Policy·WorkspaceEnv·ExecutionRuntime·FilePatch를 남겼다. Wave 2는 **도구 노출 축소·기억/스킬·오케스트레이션·Provider 경계·IRIS 고유 기능 선별 흡수**다. 구현은 단위별 TDD·fresh poteto-agent·메인 재검증 순으로만 진행한다.

## 2. 확인한 사실 (Wave 1 착지)

| 항목 | 측정/확인 |
|---|---|
| HEAD 계열 | `819c42f` 기준 작업 트리 (dff0b06 후손) |
| PIN | `a382af23f4c067d23463b5781958684c2cda82bc` |
| PHASE4 / absorbed / strip | 116 / 8 / 15 (process_manage·apply_patch 흡수 후) |
| Schema chars | home 22385 / ide 22126 (`_check_tool_contract`) |
| 계약 체크 | policy · workspace_env · execution_runtime · file_patch · tool_contract · baseline · product_residue green |
| Live 벤치 메트릭 | U00 공란 유지 (라이브 모델 벤치 미실행) |
| IrisToolContract.profiles | 필드만 존재, 라우팅 없음 → **U07 자리** |

## 3. 구조

```
[모델]
  engine_tool_schemas(surface, profile?)   ← U07 확장
       │
[SpeakTools / IrisToolContract]  U02 SSOT
       │
  ┌────┴────┬────────────┬──────────────┐
  │         │            │              │
Control   Runtime     FilePatch      Memory/Skill  ← U08
Policy    (U05)       (U06)          Orchestration ← U09
  │
Provider Adapter (canonical messages)  ← U10
  │
Browser / Aloha / Routine / Vision     ← U11 (제품 유지 + 선별 흡수)
```

## 4. 코드 리뷰 (Wave 2가 얹힐 지점)

| 지점 | 파일 | Wave 1 상태 | Wave 2 할 일 |
|---|---|---|---|
| 스키마 방출 | `speak_capability.engine_tool_schemas` | surface만 | profile ∩ grants 필터 + `tool_search` |
| profiles 필드 | `IrisToolContract` / SpeakGrant | 기본 빈 frozenset | Core/Coding/… 태깅 |
| 오류 예산 | `engine/tool_error_budget.py` | 단일 버짓 | 오류 유형별 분기 (U07) |
| Strip 잔여 | `absorbed_tool_aliases.STRIP_ONLY` | 15개 | U08/U09에서 todo/clarify/skills/memory 선별 흡수 |
| 기억 | Wiki SQLite · `chat.search_past` | 제품 소유 | Memory interface, 중복 저장소 금지 |
| MCP | gateway 제품 경로 제거됨 | — | Extension만 (U10), 필수 의존 금지 |

하지 않은 일: Dynamic profile 라우팅, Subagent, Trajectory, Headless CLI.

## 5. 단위 브리프

### U07 — Agent Performance Optimization

**Depends on:** U02, U05, U06; Wave 1.1 gate (W11-H) green (2026-11-25 evidence `wave11h-20261125-022556`, wave2_gate=go) — U05 경로는 Runtime-wired  

**Files:** `speak_capability.py`, sidecar schema install, `tool_error_budget.py`, 신규 `_check_tool_profiles.py`  
**Change:**
- Profile 집합: `core|coding|research|personal|automation|computer|extension`
- 기본 활성 = core + 요청/워크스페이스 힌트로 1–2 프로파일 (키워드 강제 금지; 힌트+tool_search)
- `tool_search` Control/Speak로 숨은 도구 활성화
- 읽기 전용·`parallel_safe` 도구만 병렬 (Provider 지원 시)
- Context compression: Hermes 모듈 존재 시 검토, IRIS 세션과 중복 저장 금지; 목표·승인·경로·미완 작업 보존
- Prompt-cache 친화: 시스템/도구 스키마 안정 정렬

**Verify:**
- Unit: profile 필터 시 schema chars < Wave1 home 22385의 유의미 감소; 필요한 도구 tool_search로 복구
- Live: 코딩 요청에 emulator/email 전체 스키마 미포함
- Perf: U00 벤치가 채워진 뒤에만 “향상” 주장; 없으면 chars·tool error만 보고

### U08 — Memory & Skill Engine

**Depends on:** U07  
**Files:** Wiki/chat search, Aloha skill 경로, strip `memory|skills_*|skill_*`  
**Change:** Working/Conversation/Semantic/Procedural/Preferences/Project 구분. 소유권은 IRIS SQLite·Wiki. Hermes memory_manager는 인터페이스만 차용. Aloha ≠ Agent Skill. 모델 생성 스킬은 미신뢰.

**Verify:** 절차 저장→재사용 1회; 권한 우회 없음; 중복 DB 없음.

### U09 — Orchestration

**Depends on:** U07  
**Files:** todo/clarify/delegate absorb, `ide.project_log`와 계획 상태 분리  
**Change:** Task state machine; clarify 구조화 질문; Subagent는 독립 context·권한 상속 상한·깊이/토큰/동시수 제한. 단순 작업에 강제 금지.

**Verify:** todo CRUD; clarify headless에서 awaiting; subagent 한도 assert.

### U10 — Provider & MCP Interoperability

**Depends on:** U02  
**Files:** provider adapters, optional MCP client  
**Change:** Canonical message model; OpenAI-compatible + 기존 Ollama 경로. MCP는 Extension 프로파일. 제품 InternalSidecar 필수 유지.

**Verify:** 도구 계약 2개 이상 Provider; MCP 없이 제품 턴 OK; 이름 충돌 없음.

### U11 — Extended Capabilities

**Depends on:** U07  
**Files:** web/browser, Aloha, Routine, vision attach  
**Change:** web_search vs browser 목적 분리; Routine 유지 + cron 기술 선별; vision 공통 인터페이스; computer_use는 IRIS로 불가한 GUI만 검토.

**Verify:** IRIS 고유 도구 회귀; 중복 TTS/이미지 생성 미노출.

## 6. 개선안 (빈 자리)

1. Profile 태그가 grant에 비어 있음.
2. Strip 15개 중 Wave2 흡수 대상이 아직 strip.
3. Live 벤치 공란 → U07 perf 게이트 미가동.
4. Compression/Subagent 코드 없음.

## 7. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Hermes conversation compression | 요약 알고리즘 | PIN 트리 부재 시 IRIS 얇은 압축 먼저 |
| Hermes todo_list / clarify | 스키마·상태 | U09에서 흡수; IDE project_log와 분리 |
| Hermes skills_* | procedural skill 파일 형식 | U08; Aloha와 동일시 금지 |
| MCP protocol | tools/list·call만 | 제품 필수 경로 복구 금지 |
| Agent Skills SKILL.md | 문서형 스킬 | 실행 권한은 Policy 경유 |

## 8. 조치

1. U07부터 실패 체크 → 구현 → Wave1 체크 회귀.
2. 단위마다 `docs/code-review/` 짧은 prove 노트; 완료 시 `completed/`.
3. 라이브 벤치 가능 시 baseline §9 공란만 채운 뒤 U07 perf 비교.
4. Wave 2 전부 green 후 Wave 3 브리프 실행으로 전환 ([wave3 brief](iris-agent-unified-runtime-wave3-brief.md)).
