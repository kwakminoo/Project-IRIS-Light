# Iris Agent Phase 5 — Prove 1 (스레드 경계·시그널만)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-P5-PROVE1 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Phase5-in-process-검증계획.md`, Prove 0 PASS |
| 대상 | 워커→UI 경계 (시그널만, UI 비블로킹, 슬롯 예외 봉쇄) |
| 목적 | 에이전트 워커가 UI 스레드를 막지 않고, 예외가 MainWindow 슬롯로 안 새는지 증거로 확정 |

## 1. 결론

Prove 1 **PASS**.  
워커→UI 는 `finished_ok` / `failed` 시그널만. `run()` 최외곽에서 예외를 `failed` 로 보낸다.  
UI 슬롯은 `safe_agent_ui_slot` 로 감싸 예외가 슬롯 밖으로 나가지 않게 했다.  
의도적 bad-path(`prove1_ui_abort_if_uncaught`)는 라이브 MainWindow 에 연결되지 않는다.  
HTTP `:8642` 제품 경로는 유지. **Merge 금지. Prove 2 미착수.**

## 2. 확인한 사실

| 항목 | 결과 |
|---|---|
| 시그널 계약 | `IRIS_AGENT_LOOP_UI_SIGNALS = {finished_ok, failed}` |
| 워커 예외 | `force_fail=True` → `failed` 수신, `finished_ok` 없음 |
| 슬롯 봉쇄 | 슬롯 본문 raise → `safe_agent_ui_slot` 이 흡수 (프로세스 생존) |
| UI 비블로킹 | 워커 `settle_ms=120` 동안 UI `QTimer` ticks ≥ 3 |
| QWidget / sync UI | `agent_runtime`·워커 `run` 소스에 위젯·`processEvents` 없음 |
| `:8642` | 제품 `HermesChatWorker` 경로 잔존 |
| 자검 | `_check_iris_agent_phase5_prove1` + prove0 PASS |

## 3. 구조

```
[Agent 워커 스레드]
  IrisAgentLoopStandinWorker.run
       │ try/except
       ├─ settle_ms (선택, 자검용)
       ├─ force_fail → raise → failed.emit
       └─ run_agent_loop_standin → finished_ok.emit
              │
              │  pyqtSignal 만 (IRIS_AGENT_LOOP_UI_SIGNALS)
              ▼
[UI 스레드]
  safe_agent_ui_slot(슬롯)  ──▶  화면 갱신
       └── 슬롯 예외는 흡수 (0xC0000409 방지)

[의도적 bad-path — 연결 금지]
  prove1_ui_abort_if_uncaught  (라이브 슬롯 미연결, 자검만)

[그대로 유지]
  HermesChatWorker ──HTTP──▶ :8642
```

갈림: Prove 1 은 **경계 계약** 만. 제품 speak 기본 경로·Merge·Prove 2(no-console) 는 하지 않음.

## 4. 코드 리뷰

| 지점 | 한 일 | 막지 못한 / 하지 않은 일 |
|---|---|---|
| `IrisAgentLoopStandinWorker` | `force_fail` / `settle_ms`, 시그널 계약 문서화 | 실제 Hermes 루프·툴 턴 |
| `IRIS_AGENT_LOOP_UI_SIGNALS` | 허용 시그널 집합 고정 | Merge 후 chunk 시그널 확장 |
| `safe_agent_ui_slot` | UI 슬롯 예외 흡수 | MainWindow 전 슬롯 일괄 적용 아님 |
| `prove1_ui_abort_if_uncaught` | 의도적 abort 샘플, UI 모듈 미참조 자검 | Prove 2 프로세스 생존 범위 |
| `run_agent_loop_standin` | docstring 에 시그널-only·슬롯 금지 | 동기 UI 호출 런타임 가드 |
| `_check_…_prove1` | 소스·시그널·봉쇄·비블로킹·8642 유지 | 실 LLM 대기 프리즈 |
| `HermesChatWorker` / gateway | **손대지 않음** | — |

## 5. 개선안

1. Prove 2 — no-console + 에이전트 예외 → failed 봉쇄·프로세스 kill 금지.
2. Prove 3 — UI 유지 + 워커/루프 리셋 + pin 동일성.
3. Merge 채팅에서만 speak 기본을 in-process 로. 그 전 `:8642` 삭제 금지.
4. Merge 전 `safe_agent_ui_slot` 을 실제 speak 슬롯에만 연결 (클릭≠에이전트 턴 유지).

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| `HermesChatWorker` | QThread + pyqtSignal + try/except→failed | 새 프레임워크 불필요 |
| Qt `QThreadPool` / `QtConcurrent` | — | 기존 워커 패턴과 이중화 |
| `concurrent.futures` | — | UI 연동은 Qt signal 이 이미 있음 |
| 별 프로세스 sandbox | — | 합침 목표와 반대. 예외 봉쇄로 대체 |

## 7. 남은 프리즈·abort 위험 (Merge 전)

| 위험 | 상태 |
|---|---|
| 제품 speak 가 아직 HTTP 워커 | 정상(미병합). UI 스레드에서 `stream_chat` 직접 호출하면 프리즈 가능 |
| 스탠드인·`settle_ms` ≠ 실 LLM 대기 | 실 루프 붙이면 워커 전용 유지 재확인 필요 |
| `safe_agent_ui_slot` 미연결 슬롯 | 기존 MainWindow 슬롯은 별 계약. 에이전트 브리지만 이번 범위 |
| `BaseException` (SystemExit 등) | 워커는 `Exception` 만 포착 — Prove 2에서 재검토 |

## 8. 조치

1. 코드·자검·본 보고서 완료.
2. 검증계획 Prove 1 체크만 갱신.
3. Prove 2 는 **새 채팅**에서만. Merge 금지.
