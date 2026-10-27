# Iris Agent Phase 5 — Prove 2 (no-console + 예외 봉쇄)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-P5-PROVE2 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Phase5-in-process-검증계획.md`, Prove 0·1 PASS |
| 대상 | 에이전트 경로 콘솔 억제 + 예외 봉쇄(프로세스 kill 금지) |
| 목적 | 워커 예외가 failed로 끝나고, 에이전트 경로가 no-console 계약을 재사용하는지 증거로 확정 |

## 1. 결론

Prove 2 **PASS**.  
에이전트 워커·스탠드인 진입에서 `ensure_agent_loop_no_console`(CREATE_NO_WINDOW 패치)를 재사용한다.  
`Exception` 은 `format_agent_loop_failure` 페이로드로 `failed` 에 봉쇄되고, 프로세스는 살아 있다.  
`SystemExit` / `KeyboardInterrupt` 는 `AGENT_LOOP_PROPAGATE_BASE` 로 재전파한다(잘못 삼키지 않음).  
HTTP `:8642` 제품 경로·Merge·Prove 3 는 하지 않았다.

## 2. 확인한 사실

| 항목 | 결과 |
|---|---|
| no-console | `ensure_agent_loop_no_console` → `install_no_console_subprocess_patch`; `no_window_kwargs` 에 CREATE_NO_WINDOW |
| 예외 봉쇄 | `force_fail=True` → `agent_failed\|RuntimeError\|…` failed; PID 유지 |
| ok=False | `standin_force_fail` → 스탠드인 오류 결과 → failed (kill 없음) |
| BaseException 정책 | Exception → failed; SystemExit/KeyboardInterrupt → raise |
| `:8642` | 제품 `HermesChatWorker` 경로 잔존 |
| 자검 | `_check_iris_agent_phase5_prove2` + prove0 + prove1 + `tests.test_no_console_window` |

## 3. 구조

```
[Agent 워커 스레드]
  IrisAgentLoopStandinWorker.run
       │ ensure_agent_loop_no_console  (CREATE_NO_WINDOW 재사용)
       │ try
       ├─ force_fail → raise Exception → format → failed.emit
       ├─ standin_force_fail → ok=False messages → failed.emit
       └─ run_agent_loop_standin → finished_ok.emit
       except AGENT_LOOP_PROPAGATE_BASE → raise
       except Exception → failed.emit(agent_failed|Type|msg)

[스탠드인]
  ensure_agent_loop_no_console
  force_fail → AgentLoopStandinResult(ok=False, messages=payload…)

[그대로 유지]
  HermesChatWorker ──HTTP──▶ :8642
  safe_agent_ui_slot = agent-bridge only
```

갈림: Prove 2 는 **봉쇄·콘솔** 만. 루프 리셋(Prove 3)·Merge·speak 기본 전환 금지.

## 4. 코드 리뷰

| 지점 | 한 일 | 막지 못한 / 하지 않은 일 |
|---|---|---|
| `format_agent_loop_failure` / `AGENT_LOOP_*` | 실패 페이로드·전파 정책 도메인화 | 실제 Hermes 루프 예외 종류 |
| `ensure_agent_loop_no_console` | win_subprocess 패치 재사용 | 제품 speak HTTP 경로 콘솔(기존 계약) |
| `run_agent_loop_standin` | force_fail→ok=False; no_console 진입 | 실 툴 subprocess 호출 |
| `IrisAgentLoopStandinWorker` | 봉쇄 + propagate 재raise + standin_force_fail | Prove 3 리셋 API |
| `_check_…_prove2` | no-console·봉쇄·PID·8642·정책 순서 | 실 Cascadia 창 육안(계약 자검) |
| `HermesChatWorker` / gateway | **손대지 않음** | — |
| `safe_agent_ui_slot` | 범위 유지(브리지만) | MainWindow 전 슬롯 |

## 5. 개선안

1. Prove 3 — UI 유지 + 워커/루프 리셋 + pin 동일성 · Merge 허용? 한 줄.
2. Merge 채팅에서만 speak 기본을 in-process 로. 그 전 `:8642` 삭제 금지.
3. 실 루프가 subprocess 를 열면 동일 `no_window_kwargs` / 패치만 쓰게 유지.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| `iris.system.win_subprocess` | CREATE_NO_WINDOW / install patch | 새 콘솔 억제 경로 불필요 |
| Prove 1 `failed` / `safe_agent_ui_slot` | 시그널·슬롯 봉쇄 | 범위 유지 |
| 별 프로세스 sandbox | — | 합침 목표와 반대. 예외 봉쇄로 대체 |
| `concurrent.futures` | — | QThread 패턴 유지 |

## 7. 조치

1. 코드·자검·본 보고서 완료.
2. 검증계획 Prove 2 체크만 갱신.
3. Prove 3 은 **새 채팅**에서만. **Merge 금지.**
