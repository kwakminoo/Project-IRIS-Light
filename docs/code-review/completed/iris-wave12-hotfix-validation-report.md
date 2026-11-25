# IRIS Wave 1.2 Hotfix & Validation Report

| 항목 | 내용 |
|---|---|
| 문서 번호 | W12-HF-12 |
| 작성일 | 2026-11-25 |
| 관련 | HF-00 baseline · Wave 1.2 CONDITIONAL |
| 대상 | HEAD 작업 후 `main` Hotfix |
| 목적 | GO/NO-GO/CONDITIONAL/UNVERIFIED 판정 |

## 1. 결론

Wave 1.2 Hotfix P0 잔여(Trusted Context freeze, 전역 confirm 제거, request-bound 승인, 즐겨찾기/스크롤 보존, 실제 Agent Turn)를 닫았다. 판정은 **CONDITIONAL GO**다. Actual Agent Turn은 라이브 마커 턴으로 증명됐으나, 사용자 프롬프트 16시나리오 전수는 이번 세션에서 전부 수행하지 않았다(일반 대화·모델 연결·착지는 확인). Agent Core Ownership은 시작하지 않는다.

## 2. 확인한 사실

| 항목 | 결과 |
|---|---|
| 기준 HEAD (시작) | `d23f937` |
| probe_engine_python | `None` (= ready). hermes-agent venv |
| Actual Agent Turn | `wave12_hf11_strict.json` ok — marker `HF11-LIVE-1795574700` → assistant `ok` |
| `_check_execution_context` | ok |
| `_check_request_approval` | ok (workspace empty mismatch + no `rt.set_human_confirm(`) |
| `_check_shell_controller` / `_check_shell_gate` | ok |
| `_check_execution_runtime` | ok |
| `_check_terminal_output_mirror` | ok (write-only) |
| `_check_file_patch_engine` | ok (fail-closed probe) |
| `_check_transcript_scroll` / scrollbar | ok |
| `_check_model_picker_open` / favorites tests | ok |
| `dist/IRIS.exe` | thin launcher → workspace |

## 3. 구조

```text
Turn begin → freeze ExecutionContext
Tool/Control
  ├─ trusted_execution_context (frozen)
  ├─ shell_gate: block↔command map + wait(timeout)
  ├─ RequestApprovalLedger via ctx.approval_reference
  ├─ shell_controller: early bind_run + cancel watch + LiveOutputRing
  └─ Runtime / Theia write-only mirror / patch probe fail-closed
```

## 4. 코드 리뷰

| 지점 | 한 일 | 예전에 막지 못한 이유 |
|---|---|---|
| execution_context + control_bindings | turn freeze | live window rebind |
| process.manage + execution_runtime | ledger via ctx; no set_human_confirm | singleton confirm race |
| shell_gate | command-bound stash + timeout | FIFO + unbounded wait |
| shell_controller / iris_shell | early run_id + cancel Event + ring | late bind / unbounded parts |
| iris-ide-bridge-poller | write only | sendText shell input |
| patch_buffer_sync | probe ≠ clean | empty list fail-open |
| chat_panel / transcript_h1 | H1 follow-tail | hidden `_log` bar |

하지 않은 일: Hermes pin/overlay 교체, ConPTY, 신규 Shell/HUD UI, 16시나리오 전수 라이브.

## 5. 개선안 (빈 자리)

| 빈 자리 | 다음 |
|---|---|
| 16시나리오 전수 | verify-iris agent-turn feature + 스크래치 WS |
| Agent spawn vs product scrub | 계약 문서만 — 강제 통일 금지 |
| iris-agent canonical | Ownership 후속 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Wave 1.2 ledger/controller | 수명주기 | 잔여만 수정 |
| verify-iris measure | 라이브 턴 | feature 정식화는 선택 |
| Hermes Ownership | — | 후속 작업 |

## 7. 조치

1. `main` 커밋 + `origin/main` push (force 금지).
2. 완료 문서를 `docs/code-review/completed/`로 이동.
3. Agent Core Ownership은 별도 착수.
