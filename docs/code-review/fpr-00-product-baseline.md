# FPR-00 Actual Product Baseline

| 항목 | 내용 |
|---|---|
| 문서 번호 | FPR-00 |
| 작성일 | 2026-11-25 |
| 관련 | PROMPT 02 Final Product Repair · Wave 1.3 NTU-12 |
| 대상 | IRIS Light 실제 GUI · Native Tool 경로 |
| 목적 | 수정 전 실측 상태 고정. 보고서 완료만으로 정상 판정 금지 |

## 1. 결론

기준 HEAD `1ab0452` + Wave 1.3 uncommitted. Registry 권위는 유지. 제품 P0 결함의 핵심 전제는 다음이다.

1. `shell.run` auto-approve는 confirm 카드·Shell Box를 통째로 건너뛴다 (`shell_gate.should_auto_run` → `block_id=""`). process.start는 auto여도 Box를 강제 삽입한다.
2. Shell Box는 가짜 assistant 턴 `shell-{bid}`로 붙고, `finish_typing`/`end_stream`의 `_turns.pop()`에 지워질 수 있다. DB 미착지.
3. `process.manage` start는 Control 경로에서 동작한다(실측 `run_id` 반환). 모델 실패는 argv/shell XOR·non-list argv·스키마 노출(`write_stdin` stub) 쪽이 본체.
4. 실패 턴은 `_land_assistant_db`를 타지 않는다. Browser는 `source=human`을 모델 args로 위조 가능. Email은 draft API 없고 Ok=보내기.

## 2. 확인한 사실

| 항목 | 결과 | 근거 | 판정 |
|---|---|---|---|
| HEAD | `1ab0452aff9c25c9e9871d1917e3d8dde6ae03b8` | `git rev-parse HEAD` | measured |
| Wave 1.3 코드 | uncommitted on main | `git status` | measured |
| Hermes registry 차단 | ok `blocked=apply_patch,clarify,patch` | `_check_native_tool_hermes_disabled` | pass |
| Absorbed wire | home_n=115 ide_n=115 | `_check_absorbed_tool_wire` | pass |
| Native binding | ok | `_check_native_tool_binding` | pass |
| shell_controller / shell_gate / execution_context | ok | module checks | pass |
| Doctor | control.live true after launch | verify-iris doctor | pass |
| Wave13 GUI tool turn | terminal→shell.run owner=iris cid=400 | `gui_tool_turn.json` | pass (routing) |
| Shell Box H1 DOM | 재시작 후 `echo FPR01-LIVE-BOX` Box 표시 | Control + GUI 스크린샷 | pass (FPR-01 후) |
| Process Manager start | 조사 중 | explore agent | open |
| 사용자 13테스트 재현 | 대기 | — | open |

## 3. 도메인 형태 (Feature architect)

| 단위 | 형태 | 소유자 |
|---|---|---|
| Shell 실행 UI | `ShellRequest(request_id, block_id, run_id, session, workspace, status, command)` → `ToolShellPart` | shell_controller |
| Process 계약 | action enum + XOR(argv\|shell); write_stdin=unsupported | process.manage + ExecutionRuntime |
| 최종 실행 계획 | tool_call_id + request_id + session + workspace + exe/argv/shell + cwd | RequestApprovalLedger.consume |
| 승인 분류 | READ_ONLY / SCOPED_MUTATION / SHELL / EXTERNAL / SENSITIVE | 기존 ToolSpec+policy 확장 |
| Turn 종료 | completed\|partial\|failed\|cancelled\|interrupted → DB land | chat landing |

## 4. Throughput checkpoint

| 차원 | 내용 |
|---|---|
| Blocking first | FPR-00 실재현 + Registry 유지 확인(완료) → FPR-01 Shell Box |
| Independent | FPR-05 Code/AppHost, FPR-10 Email (공유 파일 적음) |
| Shared mutable | shell_controller, request_approval, execution_runtime, transcript_h1 → FPR-01→02→03→07/08 직렬 |
| Smallest decomposition | Unit A Shell visibility → Unit B Process contract → Unit C Ledger consume → Unit D Landing → Unit E Approval UI → Unit F Browser → Unit G Email → Gate tests |

## 5. 조치

1. Explore 결과로 실패 증상 표 채움.
2. 살아 있는 Iris에서 Shell/승인/모델 UI 스냅샷.
3. Unit A부터 poteto-agent TDD.
