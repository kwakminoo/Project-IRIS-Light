# IRIS Wave 1.2 Final Report

| 항목 | 내용 |
|---|---|
| 문서 번호 | W12-13 |
| 작성일 | 2026-11-25 |
| 관련 | Wave 1.1 `808b313` → Wave 1.2 |
| 대상 | Trusted Context · Request Approval · H1 Shell · IDE stream · Patch sync · Gate |
| 목적 | Wave 2 GO/NO-GO/CONDITIONAL 판정 |

## 1. 결론

Wave 1.2 계획 단위(U00–U13)를 로컬 `main`에 닫았다. Shell Box는 신규 UI 없이 H1에 연결됐고, ACL은 Trusted ExecutionContext만 믿으며, 승인은 request-scoped ledger로 격리되고, Shell HUD는 fail-closed다. IDE는 Runtime 출력을 `appendTerminalOutput`으로 미러한다(재실행 없음). Patch buffer는 Theia dirty 거절·reload 경로가 살아 있다.

**Wave2 판정: CONDITIONAL** — agent_turn 라이브 미증명(엔진 probe `None`). 그 외 P0 `_check_*`·prove_feature는 PASS.

## 2. 확인한 사실

| 항목 | 결과 |
|---|---|
| `_check_shell_gate` / `_check_run_approval` / `_check_shell_controller` | ok |
| `_check_request_approval` / `_check_execution_runtime` / `_check_execution_policy` | ok |
| `_check_file_patch_engine` / `_check_workspace_shell_sync` / `_check_run_path_runtime_wire` | ok |
| `_check_tool_contract` / `_check_control_http_contract` / `_check_agent_confirm_path` | ok |
| `_check_transcript_h1` / `_check_card_html` / `_check_file_drop` | ok |
| prove startup / control-http / no-console | ok (`wave12-u12`, `wave12-u12b`) |
| doctor | ok; control.live=false |
| iris-ide bundle | `appendTerminalOutput` 포함 (install runtime) |
| agent probe | `None` → agent_turn UNVERIFIED |

## 3. 구조

```text
Agent/Control invoke
  └─ human_confirm_decision
       ├─ try_card_confirm → H1 ToolShellPart (block_id)
       └─ shell/project: card 없으면 False (HUD 금지)
  └─ shell.run / project.run / process.manage
       ├─ ExecutionContext (Control only) → Runtime ACL
       ├─ RequestApprovalLedger (fingerprint+session+cwd)
       ├─ shell_controller (request↔block↔run)
       └─ Runtime start/wait
            └─ project.run: append_terminal_output chunks (same run_id)
```

분기: Home=`shell.run`+H1 Box / IDE=`project.run`+Theia mirror / process=`manage`+ledger. LiveActivity는 모니터만.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 예전에 막지 못한 이유 |
|---|---|---|
| `transcript_h1` + `chat_panel` | insert/replace → H1 | Shell이 숨긴 `_log`에만 그려짐 |
| `chat_renderer` phase / URL | pending·iris-run 스키마 | phase kwargs TypeError |
| `execution_context` | 모델 session/owner/root 무시 | ACL이 tool args 신뢰 |
| `request_approval` | 요청 단위 grant/consume | `set_human_confirm(True)` 전역 |
| `shell_gate` / bindings | fail-closed · FIFO stash | HUD fail-open |
| `shell_controller` | request↔block↔run | 중복 Box/실행 추적 없음 |
| `project.py` + bridge | Runtime chunk mirror | `echo IRIS_RUN_ID` only |
| `patch_buffer_sync` | dirty Conflict · reload | `ide_refresh: stub` |
| `.gitignore` + hygiene tests | 추적 잡음 제거 | graphify-out 등 대량 추적 |

하지 않은 일: ConPTY, 신규 Shell/Live Panel, Hermes 되돌리기, History rewrite, 신규 유료 모델 키.

## 5. 개선안 (빈 자리만)

| 빈 자리 | 다음 |
|---|---|
| agent_turn 라이브 | 엔진 준비 후 S-agent-turn 1회 |
| Theia `write` vs `sendText` | 터미널 위젯 write API 안정화 |
| GUI 육안 pending 버튼 | 운영 Iris 세션 1회 |
| control-http 구식 소스 scrape | 함수 계약 assert로 교체 완료 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Cursor Shell Box UX | 3모드·Allowlist·카드 버튼 | 이미 재사용 — 신규 패널 금지 |
| Theia TerminalService | sendText/write 미러 | ConPTY PTY 세션은 범위 밖 |
| 요청-스코프 capability token | ledger fingerprint | 외부 IAM 도입 과다 |

## 7. 조치

1. `main` 커밋 + `origin/main` push (History rewrite/force 금지).
2. Wave 1.2 완료 문서를 `docs/code-review/completed/`로 이동.
3. Wave2는 agent_turn 증명 후 GO 재평가.
