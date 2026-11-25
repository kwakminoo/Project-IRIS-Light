# Wave 1.2 Baseline Audit

| 항목 | 내용 |
|---|---|
| 문서 번호 | W12-00 |
| 작성일 | 2026-11-25 |
| 관련 | Wave 1.1 `808b313`, W12 master prompt |
| 대상 | Shell Box / Execution Runtime / IDE / Patch / Hygiene |
| 목적 | 재사용·수정·제거 구분 후 Wave 1.2 구현 착수 |

## 1. 결론

Wave 1.1은 Runtime·Env·Patch(디스크)·Tool Contract를 닫았다. Wave 1.2의 핵심 잔여는 **H1에 Shell Box 미연결**, **모델 args 기반 ACL**, **전역 human_confirm**, **IDE echo-only**, **patch ide_refresh stub**, **Git 추적 잡음**이다. 신규 Shell Box·Live Panel·실행 엔진은 만들지 않는다.

## 2. 구조

### 2.1 Confirm → Shell Box → Runtime (현재)

```text
Agent/Control invoke
  └─ ActionRegistry.ask_human
       └─ human_confirm_decision (control_bindings)
            ├─ try_card_confirm (shell_gate)
            │    └─ chat.insert_tool_block ──► ChatLog QTextEdit (_log.hide)  ← 비가시
            │         [H1TranscriptHost: Shell 경로 없음]
            └─ (카드 실패) run_hud_confirm HUD
  └─ shell.run / project.run / process.manage
       └─ start_managed_run / ProcessRegistry.manage
            └─ ProcessRecord(session_id, owner from tool args)  ← 비신뢰 입력
```

### 2.2 표면별 역할

| 표면 | 역할 | Wave 1.2 |
|---|---|---|
| ToolShellBlock + card_html | 승인·명령·출력 카드 | **재사용**, H1에 연결 |
| LiveActivityPanel | 턴 활동 모니터 | **유지**, Shell과 합치지 않음 |
| H1TranscriptHost | 가시 채팅 | ShellPart adapter **추가** |
| ChatLog `_log` | 숨긴 legacy | tool 페인트 **중단** |
| ExecutionRuntime | 프로세스 권위 | **재사용**, Context ACL 보강 |
| Theia sendText | 터미널 write | 스트림 미러 **확장** (ConPTY 제외) |

### 2.3 호출 분기

| 진입 | 승인 | 실행 | IDE 표시 |
|---|---|---|---|
| Home `shell.run` | try_card_confirm → HUD fallback | iris_shell + Runtime | 없음 |
| IDE `project.run` | human_confirm | start_managed_run | `echo IRIS_RUN_ID=` only |
| `process.manage` start | card only (no HUD) | manage + `set_human_confirm(True)` | 없음 |
| 사용자 IDE Terminal | 해당 없음 | Theia 직접 | 기존 유지 |

## 3. 코드 리뷰 (증상별)

| 지점 | 한 일 | 막지 못한 이유 |
|---|---|---|
| `chat_panel.insert_tool_block` | HTML을 `_log`에 insert | `_log.hide()` — 제품 H1과 분리 |
| `render_tool_shell` | 래퍼 HTML | `phase` kwargs 미지원 → `_check_shell_gate` TypeError |
| `ChatPanel.replace_tool_block` | 없음 | `run_shell_live`/`gate`가 getattr만 — 부분 갱신 실패 |
| `handle_shell_approval_click` | 존재 | H1/ChatLog mouse 경로 미배선 |
| `_session_acl_allows` | session/owner 비교 | caller 값을 **tool args**에서 읽음 |
| `process.py` 승인 후 | Runtime 게이트 스킵 | 전역 `set_human_confirm(lambda: True)` |
| `SHELL_CONFIRM_BLOCK_ATTR` | 단일 block stash | 병렬 요청 시 혼선 |
| `project.run` IDE | Runtime 실행 연결 | 시각화만 echo — stdout 테일 없음 |
| `patch_buffer_sync` | 훅 프로토콜 | 제품 미등록, `ide_refresh: stub` |
| `.gitignore` | 일부 AVD/tmp | graphify/.tmp/.iris 미무시 — ~1583 tracked |

### 하지 않은 일

- Wave 2 Dynamic Tools / Memory / Subagent
- ConPTY / 대화형 stdin
- H1 transcript 전면 재작성
- 신규 Live Panel

## 4. 개선안 (빈 자리만)

1. Trusted `ExecutionContext` — Control/Agent만 생성, ACL 근거.
2. Request-scoped approval ledger — 전역 confirm·단일 stash 제거.
3. H1 Shell adapter — insert/replace/클릭을 가시 면에 연결 (`phase` 수정 포함).
4. Allowlist — 복합 명령·인터프리터 단독 prefix 자동승인 차단.
5. Shell Controller — request_id↔block_id↔run_id, HUD shell 경로 제거(fail-closed).
6. IDE Runtime 출력 미러 — echo-only 제거.
7. Patch → Theia dirty/reload 실연동.
8. Git hygiene — ignore + `rm --cached` + GitHygieneTests.

## 5. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| 기존 `shell_card_to_html` / RUN_MODES | 디자인·버튼·모드 UI 전부 | 신규 Shell Box 불필요 |
| 기존 `run_shell_live` paint 간격 | ~80ms coalescing | 엔진 재작성 불필요 |
| Theia `TerminalWidget.sendText` | 출력 미러 채널 | ConPTY 호스트 스왑은 미해결·범위 밖 |
| Cursor Allowlist 개념 | 모드 3종 UX | OS sandbox 주장 금지 |
| 찾지 못함 | in-repo Theia dirty-buffer notify | Bridge에 reload API를 최소 추가 |

## 6. 재사용 / 수정 / 제거

| 구분 | 항목 |
|---|---|
| **재사용** | ToolShellBlock, card_html, shell_approval.json, RUN_MODES, try_card_confirm, arm/decide/take, ExecutionRuntime, WorkspaceEnvironmentResolver, build_child_env, file_patch atomic/rollback, LiveActivityPanel, verify-iris |
| **수정** | insert/replace→H1, render phase, ACL←Context, request approval, allowlist 정규화, project.run 스트림, patch_buffer_sync wire, .gitignore |
| **제거** | Shell 전용 HUD fallback(공통 컨트롤러 green 후), hidden `_log` tool 페인트, echo-only 시각화(스트림 검증 후), 전역 confirm True 우회 |

## 7. Wave 1.1 대비 신규 구현 필요

이미 완료(중복 금지): Runtime wire, env scrub, patch disk, tool contract 확대, process ACL(단위·취약).

신규: Trusted Context, Request-scoped Approval, H1 Shell, Allowlist 보강, Shell HUD 제거, IDE stream, patch IDE sync, hygiene, live agent_turn + Pre-Wave2 baseline.
