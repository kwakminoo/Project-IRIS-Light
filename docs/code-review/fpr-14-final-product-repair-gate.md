# FPR-14 Final Product Repair & Unified Approval — Gate

| 항목 | 내용 |
|---|---|
| 문서 번호 | FPR-14 |
| 작성일 | 2026-11-25 |
| 관련 | PROMPT 02 · Wave 1.3 NTU-12 · FPR-00~13 |
| 대상 | IRIS Light 실제 제품 경로 |
| 목적 | 제품 결함 복구·통합 승인·회귀 판정 (GO/CONDITIONAL/NO-GO) |

## 1. 결론

**판정: CONDITIONAL** (코드 잔여 닫힘 · 라이브 13전수는 미완)

1차 게이트 이후 잔여 구현도 닫았다. stale_ref 1회 복구, SENSITIVE Always Allow 숨김, email.add/remove_account 인챗 카드, cancel/interrupted DB land. Registry·Shell Box·Process·fail land·Workspace는 유지. 사용자 13+라이브 모델 전수와 IDE Hotfix 실측 일부는 아직 UNVERIFIED라 완전 GO는 아니다. PROMPT 03 자동 시작 없음. 커밋·push 없음.

원칙: **Prove It Works**, **Fix Root Causes**, **Laziness Protocol**.

## 2. 확인한 사실

| 항목 | 결과 | 근거 |
|---|---|---|
| 기준 HEAD | `1ab0452` + Wave 1.3 uncommitted | `git rev-parse` / status |
| Hermes registry | blocked | `_check_native_tool_hermes_disabled` |
| Absorbed wire | home/ide 115 | `_check_absorbed_tool_wire` |
| Shell Box 실 GUI | `echo FPR01-LIVE-BOX` Box 표시 (재시작 후) | Control invoke + 스크린샷 |
| process.manage list/start | ok / run_id 반환 | Control HTTP |
| Fail DB land | contract ok | `_check_chat_landing_contract` |
| Browser forge | source=human 무시 | `_check_intent` + 19 unittest |
| Email draft | compose 프리필, send 미호출 | `_check_email_compose` |
| Workspace vs Agent Core | distinct interpreters | `_check_workspace_environment` |
| Code/App Host | part_contract + transcript checks ok | unittest / `_check_transcript_*` |

## 3. 구조

```text
Model tool
  → IRIS native binding (Wave 1.3)
       → Control action
            ├─ shell.run / process.manage start
            │     → shell_gate card (auto: wait skip, Box keep)
            │     → RequestApprovalLedger.grant/consume (session/workspace/fp[/tool_call_id])
            │     → ExecutionRuntime / iris_shell
            │     → ToolShellPart → H1 DOM
            ├─ email.send / browser sensitive
            │     → try_card_confirm(allow_auto=False)  ※ HUD 제거(해당 액션)
            └─ fail turn
                  → _land_failed_turn ([IRIS System Error] envelope)
```

## 4. 코드 리뷰 (단위별)

| 단위 | 한 일 | 막지 못한/잔여 |
|---|---|---|
| FPR-01 Shell Box | auto에도 Box 삽입; paint 로그; ToolShell 턴 pop 금지 | 다중 shell DOM patch는 full render 폴백 |
| FPR-02 Process | XOR 정규화; write_stdin 스키마 제거; round-trip check | write_stdin 메서드 스텁 잔존 |
| FPR-03 Ledger | consume tool_call_id; command-string fallback 제거 | grant에 tool_call_id 비어 있으면 omit |
| FPR-04 Workspace | Agent Core silent leak 차단 | Agent Home 사용자 파일은 보고만 |
| FPR-05 Code/App | 재검증 pass (변경 최소) | 라이브 모델 fence 재현은 FPR-13 잔여 |
| FPR-06 Landing | fail→DB land | sidecar hang 체크 별개 |
| FPR-07/08 Approval | email.send·browser 민감→카드 | — |
| FPR-07/08 residual | Always Allow 숨김(`allow_always`); add/remove_account 카드 | 기타 confirm_required HUD 잔여 |
| FPR-09 Browser | source forge 차단 | — |
| FPR-09 residual | stale_ref → snapshot→1회 retry / needs_reapproval | bbox 없는 role/name 매칭 |
| FPR-10 Email | draft 프리필 | SMTP cc/bcc·ledger fingerprint 미연결 |
| FPR-06 residual | cancel/interrupted DB land | conversation_reset clear는 land 생략(의도) |

하지 않은 일: PROMPT 03, commit/push, H1 전면 재작성, Hermes handler 복원, 사용자 DB 초기화, Agent Home 파일 삭제.

## 5. 개선안 (빈 자리)

| 빈 자리 | 다음 |
|---|---|
| FPR-13 전수 | 13+추가 테스트를 테스트 Workspace에서 라이브 모델로 증거 표 채움 |
| FPR-11 | LiveOutputRing·IDE mirror·dirty patch 실측 묶음 |
| Sidecar hang check | `_check_sidecar_done_landing` hang-after-Turn-ended (사전/환경) |
| 잔여 HUD | chat.clear_history, attachment move/copy, scaffold 등 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| SPIFFE-like attestation | 프로세스 간 actor 증명 | Control principal + forge ignore로 충분 |
| OpenAI Responses approval cards | 범용 승인 카드 스키마 | 기존 Shell Box/shell_gate 재사용이 계약 |
| 찾지 못함 | FPR 전용 “unified in-chat approval” 패키지 | — |

## 7. 테스트 증거 (분리)

### Unit / Contract

모두 exit 0 (메인 재실행): shell_gate, shell_controller, agent_confirm_path, request_approval, execution_context, process_manage, execution_runtime, email_compose, browser intent, chat_landing_contract, turn_followup, workspace_environment, tool_contract, native_tool_binding, hermes_disabled, part_contract, transcript_code, transcript_app.

### Control API (live)

| 호출 | 결과 |
|---|---|
| process.manage list | ok `runs=[]` |
| process.manage start (shell) | ok + run_id |
| shell.run `echo FPR01-LIVE-BOX` | ok + request_id; **GUI Shell Box 표시** |

### Agent Turn (모델)

Wave 1.3 `gui_tool_turn.json` (cid 400, terminal→shell.run owner=iris) — 권위 증명. FPR 이후 13테스트 전수 모델 재실행은 **미완**.

### GUI

| 표면 | 결과 |
|---|---|
| Home + Live Activity + 모델 gpt-oss:20b | 기동 확인 |
| Shell Box | 재시작 후 실표시 (measured) |
| 스크롤바(H1) | `_check_transcript_h1` ok (hasScrollbarCss) | pass |
| 모델 선택창 | roster/open ok; tiers 체크를 BRAND_MIN 계약에 맞춤 | pass |
| IDE 타일·즐겨찾기 라이브 | 미검증 → UNVERIFIED |

## 8. 사용자 테스트 매실행 표 (FPR-13)

| # | 테스트 | 결과 |
|---|---|---|
| 1 | 일반 대화 | 미검증 |
| 2–3 | Wiki/Browser | 부분(코드 forge 수정; 라이브 미완) |
| 4–5 | python/cwd · 30초 출력 | Control process start 부분; 라이브 모델 미완 |
| 6–11 | IDE 경로 | 미검증 |
| 12 | process start→wait | `_check_process_manage` ok; GUI 미완 |
| 13 | email draft | `_check_email_compose` ok; GUI 미완 |
| 14–15 | Code Box / App Host | contract ok; 라이브 모델 미완 |
| 16–18 | Shell 승인·중지 | auto Box GUI ok; 수동/중지 미완 |
| 19–22 | Browser/승인 격리 | forge+stale_ref unit ok; 라이브 미완 |
| 23–24 | Error budget land / 전환 | fail+cancel/interrupt contract ok |
| 25–28 | 즐겨찾기·스크롤·dirty·Agent Home | 스크롤 contract ok; 즐겨찾기/dirty 라이브 UNVERIFIED |

## 9. 조치

1. PROMPT 03 **자동 시작 금지**. 사용자 요청 시에만.
2. 남은 게이트: **FPR-13 라이브 전수**, FPR-11 IDE Hotfix 실측, sidecar hang 환경.
3. 커밋·push는 사용자 요청 시에만.
4. Agent Home 중복 파일 정리는 별도 승인 후.

## 10. 잔여 구현 재검증 (2026-11-25 저녁)

메인 재실행 exit 0: `_check_intent` + 24 browser tests, chat_landing_contract, turn_followup, agent_confirm_path, shell_gate, hermes_disabled, process_manage, email_compose, workspace_environment, transcript_h1, model_picker_roster/open/tiers.
