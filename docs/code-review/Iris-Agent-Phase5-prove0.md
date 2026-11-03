# Iris Agent Phase 5 — Prove 0 (워커 스탠드인)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-P5-PROVE0 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Phase5-in-process-검증계획.md`, §10.1 CLOSED |
| 대상 | in-process 루프 자리의 워커 기동 가능성 |
| 목적 | QWidget 없이 워커에서 스탠드인 1턴이 도는지 증거로 확정 |

## 1. 결론

Prove 0 **PASS**.  
`run_agent_loop_standin` 이 워커 스레드에서 pin·홈만 쓰고 stub 1턴을 끝냈다.  
HTTP `:8642` 는 쓰지 않았다(stub). 제품 speak 경로(`HermesChatWorker` → gateway)는 그대로 둔다.  
**Merge 금지.** Prove 1 미착수.

## 2. 확인한 사실

| 항목 | 결과 |
|---|---|
| import | `agent_runtime` (pin/home/standin), 자검에서만 `IrisAgentLoopStandinWorker` 계약 확인 |
| HTTP `:8642` | **미사용** (mode=`stub`) |
| 병목 | stub 이라 gateway·LLM 대기 없음. 이후 진짜 루프면 import·세션 초기화가 병목 후보 |
| 자검 | `iris.system._check_iris_agent_phase5_prove0` PASS |

## 3. 구조

```
[체크 / 워커 스레드]
  run_agent_loop_standin  ──▶  load_pinned_sha + iris_agent_home
       │                         stub 1턴 (HTTP 없음)
       ▼
  AgentLoopStandinResult(ok, pin, home, mode=stub, thread_name)

[UI 쪽 자리만 — 제품 speak 아님]
  IrisAgentLoopStandinWorker(QThread).run
       └── run_agent_loop_standin  (시그널 finished_ok / failed)

[그대로 유지]
  HermesChatWorker ──HTTP──▶ :8642 gateway
```

갈림: Prove 0은 **대체 호출면(스탠드인)** 만 증명. 제품 기본 경로를 바꾸지 않음.

## 4. 코드 리뷰

| 지점 | 한 일 | 막지 못한 / 하지 않은 일 |
|---|---|---|
| `run_agent_loop_standin` | pin·홈·스레드명으로 stub 결과 | 실제 Hermes 루프·툴 턴 |
| `AgentLoopStandinResult` | mode=`stub` 고정 도메인 결과 | Merge 후 실제 루프 결과형 |
| `IrisAgentLoopStandinWorker` | QThread + signal 자리 (HermesChatWorker 패턴) | UI 연결·speak 기본 전환 |
| `_check_…_prove0` | 소스에 QWidget 금지, 워커 스레드 실행, :8642 제품 경로 잔존 확인 | Prove 1 슬롯 abort·프리즈 |
| `HermesChatWorker` / gateway | **손대지 않음** | — |

## 5. 개선안

1. Prove 1 — 워커→UI 는 pyqtSignal 만. 슬롯로 예외 안 샘.
2. Prove 2 — no-console + 예외 → failed 봉쇄.
3. Prove 3 — UI 유지 + 워커/루프 리셋 API + pin 동일성.
4. Merge 채팅에서만 speak 기본을 in-process 로. 그 전 `:8642` 삭제 금지.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| `HermesChatWorker` | QThread + pyqtSignal | 새 프레임워크 불필요 |
| `ensure_iris_agent_runtime` | pin/홈 supervisor | Prove 0 stub 는 gateway 기동 불필요 |
| `concurrent.futures` | — | threading.Thread 자검으로 충분 |
| 별 프로세스 sandbox | — | 합침 목표와 반대 |

## 7. 조치

1. 코드·자검·본 보고서 완료.
2. 검증계획 Prove 0 체크만 갱신.
3. Prove 1 은 **새 채팅**에서만.
