# Iris Agent Phase 5 — Prove 3 (핫리스타트 대체 + pin)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-P5-PROVE3 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Phase5-in-process-검증계획.md`, Prove 0·1·2 PASS |
| 대상 | UI 호스트 유지 + 워커/루프 리셋·교체 + pin == vendor PIN |
| 목적 | 엔진만 재시작하던 경우를 in-process 리셋으로 대체할 수 있는지 증거로 확정 |

## 1. 결론

Prove 3 **PASS**.  
`reset_agent_loop` / `replace_agent_loop_worker` 로 워커를 끊고 세대(generation)를 올린 뒤에도 **같은 호스트 객체**가 살아 있고, 새 워커로 스탠드인을 다시 돌릴 수 있다.  
`load_pinned_sha()` 는 vendor `PIN` 과 일치한다.  
HTTP `:8642` 제품 경로·Merge 채팅 작업은 하지 않았다.

**Merge allowed? YES** (Prove 0~3 자검 게이트). Merge 채팅은 사용자가 명시할 때만. 본 채팅에서 Merge 미착수.

## 2. 확인한 사실

| 항목 | 결과 |
|---|---|
| 호스트 생존 | `AgentLoopHost` `id` 가 reset 전후 동일 |
| 리셋 후 스탠드인 | 새 `IrisAgentLoopStandinWorker` → `finished_ok` |
| pin | `pin_matches_vendor_pin()` True; SHA == `vendor/iris-agent-runtime/PIN` |
| `:8642` | 제품 `HermesChatWorker` 경로 잔존 |
| 자검 | `_check_iris_agent_phase5_prove3` + prove0 + prove1 + prove2 |

## 3. 구조

```
[UI host — 유지]
  AgentLoopHost (또는 이후 MainWindow)
       │ sticky ref
       ▼
  AgentLoopHandle(generation, worker, ephemeral)
       │
       ├─ attach_agent_loop_worker / replace_agent_loop_worker
       │       └── IrisAgentLoopStandinWorker (QThread)
       │
       └─ reset_agent_loop
               quit/wait worker → clear ephemeral → generation++
               host 동일 · pin 자검

[그대로 유지]
  HermesChatWorker ──HTTP──▶ :8642
```

갈림: Prove 3 은 **리셋 API·커버리지 표** 만. speak 기본 전환·Merge 금지.

## 4. 핫리스타트 커버리지

| 상황 | 리셋으로 커버? | 비고 |
|---|---|---|
| gateway hang / 포트 꼬임 | `covered_by_reset` | 루프 인스턴스 dispose → 새 워커 |
| config reload (모델·provider) | `covered_by_reset` | ephemeral clear + 루프 재생성 |
| soft-hang (루프만 멈춤) | `covered_by_reset` | worker quit/wait + 새 워커, UI 유지 |
| MCP·스킬 sync 후 재연결 | `covered_by_reset` | 세션 ephemeral 리셋 |
| pin / 런타임 코드 교체 | `needs_process_restart` | 코드 리로드 한계 — 프로세스 재시작 |
| Ollama 다운 | `out_of_scope` | Ollama만 다룸 |

도메인 표: `AGENT_LOOP_RESET_COVERAGE` (`agent_runtime`).

## 5. 코드 리뷰

| 지점 | 한 일 | 막지 못한 / 하지 않은 일 |
|---|---|---|
| `AgentLoopHandle` / `AgentLoopHost` | sticky host + generation | 실 MainWindow 바인딩 |
| `reset_agent_loop` | worker stop, ephemeral clear, pin 검사 | 실 Hermes 루프 cancel 토큰 |
| `replace_agent_loop_worker` | reset + attach | Merge 후 speak 경로 연결 |
| `pin_matches_vendor_pin` | PIN 파일 == `load_pinned_sha` | PIN 승격 워크플로 |
| `_check_…_prove3` | host 생존·재실행·표·8642 | 실 soft-hang 유도(스텁 quit) |
| `HermesChatWorker` / gateway | **손대지 않음** | — |

## 6. 개선안

1. Merge 채팅에서만 speak 기본을 in-process 로. 그 전 `:8642` 삭제 금지.
2. 실 루프 cancel 토큰을 `reset_agent_loop` 와 정합.
3. pin 교체 시 프로세스 재시작이 필요함을 제품 복구 UX에 명시.

## 7. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Prove 0–2 워커·봉쇄 | QThread + failed 계약 | 범위 유지 |
| `ensure_iris_agent_runtime` | supervisor 멱등 패턴 | gateway 재기동과 분리된 루프 리셋 |
| 별 프로세스 kill | — | 합침 목표와 반대. 리셋으로 대체 |
| importlib 핫리로드 | — | pin/code swap 은 프로세스 재시작 |

## 8. 조치

1. 코드·자검·본 보고서 완료.
2. 검증계획 Prove 3·착수 조건(사용자 Merge 채팅 제외) 갱신.
3. **Merge 채팅 미착수.** 사용자가 명시할 때만.
