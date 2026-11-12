# Iris Agent Phase 5 — Merge decision

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-09-AGENT-P5-MERGE |
| 작성일 | 2026-11-09 |
| 관련 | Prove 0~3 PASS, `Iris-Agent-Phase5-in-process-검증계획.md` §9 |
| 대상 | same-process AIAgent 병합 여부 |
| 목적 | Prove 게이트 통과 후 Merge를 **확정**한다 |

## 1. 결론

**Merge same-process AIAgent into the Qt process? NO.**

제품 speak 기본은 이미 `InternalSidecar`다. Hermes `AIAgent`는 자식 프로세스(`_sidecar_main`)에서 돌고, Iris UI 워커는 `shared_engine().run_turn`으로만 말한다. HTTP `:8642` ExternalGateway는 설정 플래그일 때만 쓴다.

같은 OS 프로세스에 `AIAgent`를 import 하는 병합은 **하지 않기로 확정**한다. Prove 0~3이 증명한 것은 워커 계약·리셋 API·no-console이다. 크래시 격리와 hermes venv 분리를 버리면서까지 한 프로세스로 합치지 않는다.

§10.1 소유권 게이트 1~4는 이미 CLOSED. Phase 5 실패가 일체화 실패가 아니다.

## 2. 확인한 사실

| 항목 | 결과 | 근거 |
|---|---|---|
| Prove 0~3 | PASS | `_check_iris_agent_phase5_prove{0,1,2,3}` |
| merge_allowed | YES (게이트) | prove3 출력 |
| 제품 기본 EngineSource | InternalSidecar | `iris/engine/types.py` |
| speak 기본 경로 | sidecar IPC, not `:8642` | `HermesChatWorker._run_internal` |
| same-process AIAgent | 가능하나 채택 안 함 | project venv에서 site-packages import 실험 OK. 격리 포기 비용이 큼 |
| Live chat | OK | doctor + chat.send (2026-11-09) |

## 3. 구조 (확정)

```
[Iris Qt process]
  HermesChatWorker (QThread)
       └── shared_engine().run_turn
              └── InternalSidecar child (_sidecar_main + AIAgent)

[opt-in only]
  ExternalGateway ──HTTP──▶ :8642
```

## 4. 조치

1. 본 문서가 Phase 5 Merge 결정의 정본이다.
2. `_check_iris_agent_phase5_merge` 가 기본 InternalSidecar·영문 activity·prove 잔존을 자검한다.
3. same-process AIAgent 재논의는 새 요구가 있을 때만. 그 전에는 이 결정을 되돌리지 않는다.
