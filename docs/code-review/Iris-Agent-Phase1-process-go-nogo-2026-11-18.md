# Iris Agent Phase 1 — Process unification go/no-go

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-18-AGENT-P1-PROCESS |
| 작성일 | 2026-11-18 |
| 관련 | Phase 0 DONE (PHASE4 file tools), `completed/Iris-Agent-Phase5-merge.md` Merge NO, Prove 0~3 |
| 대상 | Qt 프로세스에 AIAgent 동일 프로세스 병합 여부 |
| 목적 | Prove 재실행 증거로 process unification go/no-go를 확정한다 |

## 1. 결론

**Decision: NO-GO.** 제품 speak는 `InternalSidecar`에 유지한다. Qt/`MainWindow`에 `AIAgent`를 넣지 않는다.

Prove 0~3은 워커 계약·슬롯 격리·no-console·리셋 API를 다시 PASS 했다. 이는 in-process 병합의 제품 이득을 증명하지 않는다. `_check_iris_agent_phase5_merge`는 FAIL 했고, 기존 Phase 5 Merge 정본은 이미 NO다. 크래시 격리와 hermes venv 분리가 InternalSidecar를 이긴다.

## 2. Prove 결과

| 명령 | 결과 | 비고 |
|---|---|---|
| `.venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove0` | PASS | stub speak, `http8642=not_used` |
| `.venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove1` | PASS | signal-only, slot-contained, product path kept |
| `.venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove2` | PASS | no-console, exception-contained, `merge=forbidden` |
| `.venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove3` | PASS | host survives reset, pin matches vendor, `merge_allowed=YES` (게이트만) |
| `.venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_merge` | FAIL | `append_instant_line("No tool calls")` 문자열 자검 불일치 |

실행일: 2026-11-18. 제품 `EngineSource`는 코드상 `InternalSidecar` 단일. 이번 세션에서 in-process 제품 경로를 켜지 않았다.

## 3. 결정

| 항목 | 내용 |
|---|---|
| 판정 | **NO-GO** |
| 제품 기본 | `InternalSidecar` (자식 `_sidecar_main` + AIAgent) |
| 하지 않은 일 | `MainWindow`/Qt에 AIAgent import, EngineSource in-process 전환 |
| Phase 0 | 유지 (건드리지 않음) |

## 4. 이유

| 근거 | 판단 |
|---|---|
| Prove 0~3 PASS | 계약·리셋·콘솔만 증명. same-process 제품 채택 근거가 아님 |
| merge 자검 FAIL | 킥오프 규칙: 체크 실패 시 NO-GO |
| Phase 5 Merge 정본 | `completed/Iris-Agent-Phase5-merge.md` — same-process Merge **NO** |
| 격리 | AIAgent 크래시·hermes venv를 Qt와 분리하는 이득이 병합보다 큼 |
| 이득 문서화 | InternalSidecar 대비 in-process의 명확한 제품 이득 없음 → GO 불가 |

## 5. 상태 — CLOSED

| 항목 | 내용 |
|---|---|
| 백로그 | **CLOSED** (2026-11-19). NO-GO를 뒤집지 않음 |
| 자검 | `_check_iris_agent_phase5_merge` (MainWindow no AIAgent), `_check_iris_agent_sidecar_only`, 통합 `_check_agent_merge_policy_closed` |
| Slot D | 별도 CLOSED: REPLACE — `_check_sidecar_disables_agent_file_terminal` |

## 6. 조치

1. 본 문서가 Phase 1 process unification go/no-go 정본이다. 상태는 CLOSED.
2. 제품 기본은 InternalSidecar를 유지한다. Qt에 AIAgent를 넣지 않는다.
3. same-process 재논의는 Prove가 PASS이고 InternalSidecar 대비 이득이 문서로 고정될 때만 연다.
4. phase5_merge 자검의 옛 activity 영문 문자열 항목은 제거됐다. 병합 금지는 MainWindow/AIAgent 부재로 잠근다.
