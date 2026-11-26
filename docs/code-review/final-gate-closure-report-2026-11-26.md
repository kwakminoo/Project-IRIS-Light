# Final Gate Closure — 실행 결과

| 항목 | 내용 |
|---|---|
| 문서 번호 | FGC-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | Wave 1 Finalization · FPR-14 · ACF |
| 대상 | IRIS Light Owned GUI · Host tool path · process.manage |
| 목적 | Final Gate Closure 4단 실행·검증 후 Wave 1 전환 판정 |

## 1. 결론

**판정: NO-GO** (전환·`legacy_migration_approved` 승격 보류)

1·2단 코드 단절은 닫혔고 계약 검사는 통과했다. 3단에서 Shell/Browser 실오류 원인을 확정했고, 스키마 별칭 수정 후 Browser 모델 왕복은 `ok:true`까지 올라왔다. 모델 `shell.run`은 스키마 장벽은 넘겼으나 실행 결과가 `exit 1 · fail`이라 Product Stability GO 조건(도구 결과 성공 + 요청 완료 답변)을 충족하지 못한다. 13+FPR GUI 전수와 기존 홈 설치 전환 증거는 없다. `legacy_migration_approved`는 `false` 유지가 맞다.

## 2. 단계 결과

### 1단 · 호출 메타데이터

| 항목 | 결과 |
|---|---|
| 결함 | Sidecar `tool_call_id` 송신 · Host는 `(action, args)`만 전달. Worker `StatelessTurn`에 session/workspace 미주입 |
| 수정 | `bind_host_tool_call_meta` → `ExecutionContext` overlay. MainWindow 캡처 → Worker → `StatelessTurn` |
| 검증 | `_check_execution_context` · `_check_native_tool_binding` · `_check_agent_turn_tools` · `_check_execution_policy` = exit 0 |

### 2단 · process.manage 계획→승인 소비

| 항목 | 결과 |
|---|---|
| 결함 | Ledger consume 후 cwd/argv bind (계획 변경 가능) |
| 수정 | `FinalizedStartPlan` finalize → consume → start. 카드 grant와 동일 fingerprint |
| 검증 | `_check_process_manage` · `_check_request_approval` · `_check_execution_runtime` · `_check_execution_context` = exit 0 |

### 3단 · Reference/Owned GUI

| 항목 | 결과 | 근거 |
|---|---|---|
| 3a 자동 계약 | PASS | hermes_disabled · absorbed 115 · tool_contract · approval · process · browser intent · email · workspace · shell_gate · confirm · landing |
| 64k 기존 증거 | routing PASS / tool FAIL | `.tmp/acf-gui-64k/gui-evidence.json` |
| 실오류 확정 | schema mismatch | shell `cmd`→`missing command`; browser `url`→`unexpected argument` |
| 스키마 별칭 | 구현·계약 PASS | `normalize_speak_invoke`: cmd/shell→command; open+url→navigate |
| Control shell/navigate | PASS | marker·navigate ok (forced retest) |
| 모델 browser_open+url | PASS | `ok:true` (`.tmp/acf-gui-64k-retest/gui-evidence.json`) |
| 모델 shell.run | FAIL | 스키마 통과 후 `exit 1 · fail`; assistant 마커 미보고 |
| 13+FPR 전수 | 미완 | 전용 러너 없음 · 수동 표 잔여 |

### 4단 · 전환 가드

| 항목 | 결과 |
|---|---|
| `legacy_migration_approved` | `false` (`vendor/iris-agent-core/SOURCE_MANIFEST.json`) |
| `_check_hermes_update` · owned_install · sidecar_only | ok |
| `tests.test_iris_owned_core_release` | 8 OK |
| 기존 홈 설치 완주·롤백 전환 | 미실시 (동등성 미달로 보류) |

## 3. 구조 (이번 수정이 끼운 자리)

```text
Sidecar TOOL_CALL (tool_call_id, args)
  → Host _reply_to_tool_request
       → bind_host_tool_call_meta (request_id, tool_call_id)
       → SpeakTools.invoke
            → normalize_speak_invoke (cmd→command, open+url→navigate)
            → validate → Control handler
                 → trusted_execution_context (+ Host overlay)
                 → shell/browser/process (process: finalize→consume→start)
```

## 4. 코드 리뷰 (한 일 / 막지 못한 일)

| 지점 | 한 일 | 막지 못한 일 |
|---|---|---|
| Host runtime | 검증 메타를 ctx에 연결 | 모델 shell exit 1 원인(실행 환경/명령) |
| Worker/MainWindow | session/workspace를 Turn에 주입 | — |
| process.manage | 계획 확정 후 consume | confirm_required HUD 잔여(clear_history 등) |
| Speak normalize | cmd/url 별칭 | Control 직호출 open+url는 Speak 밖(별도 경로; 이번 Control open+url는 ok 관측) |
| GUI 전수 | Shell/Browser 강제 재시험 | 승인/거절/장시간/IDE/즐겨찾기/Reference 동등 |

## 5. 개선안 (빈 자리)

| 빈 자리 | 다음 |
|---|---|
| 모델 shell `exit 1` | 실제 argv/cwd/shell 인터프리터와 Control 성공 경로 diff |
| 13+FPR 라이브 | 격리 profile에서 표 채움 · Reference 동일 조건 |
| 전환 | 동등성 GO 후 테스트 홈 복제본 설치·롤백 → 그다음 `legacy_migration_approved` |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| OpenAI tool arg aliases | 공식 schema aliases | Speak 경계 coerce로 충분 |
| 찾지 못함 | FGC 전용 13-scenario runner 패키지 | 기존 `_check_*` + lab 스크립트 유지 |

## 7. 조치

1. `legacy_migration_approved` **유지 false**. Wave 2 착수 금지.
2. 다음 P0: 모델 `shell.run` exit 1 루트코즈 → 성공 왕복 증거.
3. 그다음 13+FPR · Reference 동등 · 전환 가드 재판정.
4. 커밋·push는 사용자 요청 시에만.
