# Wave 1 Final Integration — Progress Checkpoint

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-26 |
| Baseline HEAD | `64bf196` (clean) |
| Live engine | Reference `hermes-agent` (Owned live 미설치) |
| Exit predicate | FIG-36 보고서 + Gate A–E 증거 + P0 수정/차단 + migration false 유지 |

## 원칙 (이번 세션 적용)

| 원칙 | 선택에 미친 영향 |
|---|---|
| Prove It Works | Manifest만으로 Owned 실행 판정 금지. `probe None`=성공으로 재해석 |
| Fix Root Causes | shell exit 1을 Runtime 재작성 대신 모델 list-literal coerce로 추적 |
| Sequence Verifiable Units | FIG-00 → FIG-05 coerce → FIG-07 workspace → 이후 Gate |
| Laziness Protocol | Native Registry/Process Manager 재작성 금지 |
| Never Block on Human | 가역 수정 진행. cutover/commit/유료 확대는 보류 |

## PHASE 00

| FIG | 상태 | 산출 |
|---|---|---|
| FIG-00 | done | `fig-00-actual-product-engine-baseline-2026-11-26.md` |
| FIG-01 | done | `fig-01-product-preservation-baseline-2026-11-26.md` |

## 계약 재실행 (이번 세션)

| Check | 결과 |
|---|---|
| `_check_tool_contract` | ok (coerce 전) |
| `_check_native_tool_binding` | ok |
| `_check_native_tool_hermes_disabled` | ok blocked=apply_patch,clarify,patch |
| `_check_absorbed_tool_wire` | ok home/ide 115 |
| `_check_process_manage` | ok |
| `_check_execution_runtime` | ok |
| `_check_request_approval` | ok |
| `_check_workspace_environment` | **FAIL** (`Path.home().resolve()` scrape) → FIG-07 |
| `_check_uv_probe_boost_no_editable` | **FAIL** (`stamp` kwarg API drift) → 잔여 |

## 진행 중 / 방금 닫힘

| 단위 | 상태 | 증거 |
|---|---|---|
| FIG-05 | **closed (contract)** | Speak list-literal coerce. `_check_tool_contract`·`_check_speak_surface_shell` exit 0 (메인 재검증). 라이브 모델 턴 UNVERIFIED |
| FIG-07 | **closed** | 체크를 `finalize_process_start_plan` 행동 assert로 교체. `_check_workspace_environment` exit 0 |
| FIG-04 audit | done (read) | P0: TOOL_RESULT 한 줄. 구현 에이전트 착수 |
| FIG-04 impl | **closed (contract)** | TOOL_RESULT + TOOL_CALL enrich. `_check_native_tool_binding` exit 0. 라이브 로그 착지 UNVERIFIED |
| FIG-00 engine | done | live=hermes Reference; Owned vendor only; probe None=성공 |
| FIG-29 | **closed (audit)** | `fig-29-hermes-residual-dependency-audit-2026-11-26.md` — REMOVE 후보 없음 |
| Gate A+ | partial | iris_shell / file_patch / execution_context / chat_landing ok |

## 게이트 정본 (보고서 교차)

최신 정본: **FGC + ACF = NO-GO**. Wave1.3 GO는 라우팅만. Cutover 금지.

## 닫힌 수리 (계약)

| FIG | 상태 |
|---|---|
| 05 shell coerce | closed |
| 04 TOOL_RESULT | closed (live log UNVERIFIED) |
| 06 terminal/process_manage/ide.edit 설명 | closed (live model pick UNVERIFIED) |
| 07 workspace check | closed |
| 08 plan.env → start(env=) | closed (timeout/environment_id still raw UNVERIFIED) |
| 29 residual audit | closed (no REMOVE) |

## FIG-02

| 항목 | 상태 |
|---|---|
| Prep doc | `fig-02-owned-vs-reference-matrix-prep-2026-11-26.md` |
| Unit A | PASS |
| HELLO 증거 셀 | Owned/Reference PASS (기존) |
| 120B Owned 패리티 | 승인 대기 |

## 다음

1. FIG-09/Gate B negative · Gate A 잔여
2. FIG-03 결정론 shell/process 최소 재현
3. 유료/상위 모델·실제 cutover는 사용자 승인 게이트
