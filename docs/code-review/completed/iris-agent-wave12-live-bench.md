# Wave 1.2 Live Agent Bench

| 항목 | 내용 |
|---|---|
| 문서 번호 | W12-12 |
| 작성일 | 2026-11-25 |
| 관련 | Wave 1.2 U12, Pre-Wave2 baseline |
| 대상 | Unit / Control / GUI harness / AgentTurn / Perf |
| 목적 | 연결 모델만으로 라이브 벤치 판정 |

## 1. 결론

Control·Unit·prove_feature(startup / control-http / no-console)는 통과했다. Iris Agent venv probe는 `None`(엔진 미준비)이라 **agent_turn = UNVERIFIED**. Wave2 게이트는 이 한 줄 때문에 **CONDITIONAL**.

## 2. Pre-Wave2 baseline (U00 고정)

| 축 | 결과 | 근거 |
|---|---|---|
| unit | PASS | `_check_shell_gate`, `_check_run_approval`, `_check_shell_controller`, `_check_request_approval`, `_check_execution_runtime`, `_check_execution_policy`, `_check_file_patch_engine`, `_check_workspace_shell_sync`, `_check_transcript_h1`, `_check_card_html` |
| control | PASS | `_check_control_http_contract`, `_check_tool_contract`, `_check_run_path_runtime_wire`, `_check_agent_confirm_path` |
| GUI harness | PASS | prove `startup` (wave12-u12), doctor `ok: true` (control.live=false — 세션 미기동) |
| agent_turn | UNVERIFIED | `probe_engine_python` → `None`; 신규 키/가입 없음(계획 기본) |
| perf | RECORDED | paint interval / ring clip 유지; 비율 주장 없음 |

증거 디렉터리: `.iris_light_test_tmp/verify-iris/wave12-u12/`, `wave12-u12b/control-http/`.

## 3. 시나리오 분류 (가능분만)

| ID | 층 | 상태 |
|---|---|---|
| S-unit-shell | Unit | 통과 |
| S-control-confirm | Control | 통과 (fail-closed no HUD) |
| S-prove-startup | GUI | 통과 |
| S-prove-control-http | Control | 통과 |
| S-prove-no-console | Unit | 통과 |
| S-agent-turn | AgentTurn | UNVERIFIED |

## 4. 조치

1. Wave2 진입 전 엔진 설치·연결 모델로 agent_turn 한 턴 재측정.
2. 라이브 Iris GUI 육안(Shell Box pending 버튼)은 운영자 세션에서 확인.
