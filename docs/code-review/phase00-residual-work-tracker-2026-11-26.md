# PHASE 00 Residual Work Tracker — IRIS Independent Native Agent

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE00-RWT-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | FIG-00/01/02/29 · FGC · ACF · FPR-14 · GPT-OSS ACF GUI · Wave1 progress |
| 대상 | Hermes 전면 흡수 후 IRIS 독립 Native Agent 잔여 작업 |
| 목적 | 게이트 문서 상태를 한 표로 고정. Development Gate 정책 아래 진행 가능 단위를 분리 |

## Development Gate 정책 (이번 트래커 권위)

권위 문서: `phase14-gate-policy-reformation-2026-11-26.md` (FINAL EXECUTION AUTHORIZATION 갱신).

| 규칙 | 적용 |
|---|---|
| 기존 **NO-GO** | **공개 릴리스**와 **전체 사용자 대상 비가역 변경**만 막는다 |
| 개발·통합 | NO-GO여도 **계속**한다. 단위 완료 ≠ 전체 종료 |
| Reference Core | 비교·복구 전용. 정상 제품 경로에서 제외. **미래 정본 아님** |
| Developer Cutover | **실행됨** (phase22). active Owned · previous hermes. 공개와 무관 |
| 금지 (KEEP) | 요청 없는 commit/push · 사용자 데이터 영구 삭제 · **전체 사용자** `legacy_migration_approved` 공개 승격 · 공개 배포 |

상태 라벨: `COMPLETE` · `PARTIAL` · `REGRESSION` · `UNVERIFIED` · `OPEN` · `KEEP` (비가역 게이트 유지).

출처 문서는 다시 쓰지 않았다. 상태만 추출·재분류했다.

---

## 1. 결론

**공개 릴리스는 여전히 NO-GO다.** 개발 홈 Owned cutover는 **COMPLETE**. live active=`iris-agent.slot-e38f3ea761714c36`, previous=`hermes-agent`. hermes 미삭제 · `legacy_migration_approved=false`. FPR13 라이브는 phase26에서 l01/l04 Owned HELLO/shell로 해제(`--include-live` 20/20). 남은 P0는 Owned 패리티. post-cutover HELLO 스모크(phase24) COMPLETE.

| 우선 | ID | 상태 | 한 줄 |
|---|---|---|---|
| P0 | R-SHELL-LIVE | COMPLETE | 격리 `gpt-oss:20b` 턴 exit 0 · TOOL_RESULT ok (`phase04-shell-live-retest`) |
| P0 | R-CUTOVER-PROOF | COMPLETE (개발) / KEEP (공개) | `.tmp/dev-cutover/evidence.json` · phase22 |
| P0 | R-13FPR-GUI | COMPLETE | 계약 16 + 라이브 4 pass (`--include-live` 20/20). l01/l04 → Owned HELLO/shell (phase26) |
| P0 | R-OWNED-PARITY | PARTIAL | FIG-03 hello+shell PASS. 도구 전수·GUI 동등·120B 승인 대기 |
| P0 | R-E-FALLBACK | COMPLETE | phase23 owned slot > hermes (selection 없을 때) |
| P0 | R-GUI-SMOKE-POST | COMPLETE | phase24 headless HELLO · Owned repo_dir · `.tmp/post-cutover-smoke/evidence.json` (실 GUI 클릭은 선택) |
| P1 | R-HERMES-RETIRE | PARTIAL | dead install.ps1 제거(phase19). 물리 삭제 KEEP |
| P1 | R-SURFACE-UNVER | UNVERIFIED | FIG-01 다수 표면 EXISTING BUT UNVERIFIED |
| KEEP | R-MIGRATE-FALSE | KEEP (전체 사용자) | 공개 migration 승격 금지 |

**닫힘 (이번 세션)**

R-OWNED-INSTALL · R-OWNED-ROLLBACK · R-FIG-03 · R-GATE-B(계약) · R-RUNNER-FIG19 · R-SHELL-ASSIST · R-CUTOVER-PROOF(개발) · R-E-FALLBACK · R-GUI-SMOKE-POST · R-FINAL-REPORT(FIG-36).

**병렬 가능**

1. R-SURFACE-UNVER / Gate D 인벤토리 (관측만)
2. R-GATE-A-REST 잔여 표면
3. R-OWNED-PARITY — 도구 전수·GUI 동등

**직렬 필수**

- R-GUI-SMOKE-POST → (승인 후) R-MIGRATE-FALSE 공개 승격
- R-HERMES-RETIRE 물리 삭제(FIG-33) → 동등성·회귀 전수 이후만

원칙: **Sequence Verifiable Units**, **Outcome-Oriented Execution**.

---

## 2. PHASE 00–15 ↔ 잔여 매핑

Full Absorption 골격은 ACF-00…15 (`iris-agent-wave1-finalization-gate.md`)다.  
Wave 1 Final Integration FIG 트랙(PHASE 00–07 / FIG-00…37)은 같은 목표의 실행 단위로 옆에 붙인다.

| PHASE | Full Absorption (ACF) | Wave1 FIG 트랙 | 잔여 ID (요약) | 단계 상태 |
|---|---|---|---|---|
| 00 | 엔진·경로 인벤토리 | FIG-00 Baseline | R-BASE-FIG00 | COMPLETE (`phase00-live-baseline`, HEAD `47c1d21`). GUI 미기동으로 PID·fingerprint PARTIAL/UNVERIFIED |
| 01 | 패키지·Manifest·lock | FIG-01 Preservation | R-PRESERVE-FIG01 | PARTIAL / 표면 UNVERIFIED |
| 02 | Clean install (Windows) | FIG-02 Matrix prep | R-MATRIX-FIG02 | PARTIAL (Unit A+HELLO). 120B OPEN(승인) |
| 03 | Slot·selection·rollback | FIG-03 Min repro | R-FIG-03 | COMPLETE (hello+shell `.tmp/fig-03/evidence.json`) |
| 04 | Wizard/Setup·업데이트 경로 | FIG-04…10 Runtime repair | R-OBS-FIG04, R-SHELL-*, R-SCHEMA-FIG06, R-WS-FIG07, R-PLAN-FIG08, R-NAT-FIG09, R-CTX-FIG10 | 계약 다수 COMPLETE. 라이브 잔여 |
| 05 | Native dispatch 차단 | (FIG-09 포함) | R-NAT-FIG09, R-ACF05 | COMPLETE(차단). 원본 파일 삭제 KEEP |
| 06 | Sidecar vs Gateway 분리 | FIG-29…33 Legacy | R-HERMES-*, R-ACF06 | PARTIAL. 물리 삭제 KEEP |
| 07 | 이름·CLI·overlay bake | FIG-31 CLI cleanup | R-ACF07 | PARTIAL |
| 08 | MCP/SOUL/Mobile 보존 | FIG-32 Integrations | R-ACF08 | PARTIAL |
| 09 | 자산 분류·비활성 도구 | FIG-32 | R-ACF09, R-ASSETS | COMPLETE(분류). 흡수 미검증 OPEN |
| 10 | 기존 사용자 마이그레이션 | FIG-27 | R-MIGRATE-FALSE | **KEEP false** |
| 11 | Reference/Owned 동등 | FIG-02/03/22/24 · Gate C/E | R-OWNED-PARITY, R-GATE-C, R-GATE-E | PARTIAL |
| 12 | Hermes checkout 없는 Owned 실행 | FIG-25/26/28 | R-OWNED-INSTALL, R-CUTOVER-PROOF | COMPLETE(격리+개발 cutover). 공개 KEEP |
| 13 | Hermes 물리 삭제 게이트 | FIG-33 | R-PHYS-DELETE | **KEEP** (조건 미충족) |
| 14 | 증거·회귀 묶음 | FIG-11…24 · FPR · Gate A–D | R-13FPR-GUI, R-GATE-*, R-FPR-* | 계약+라이브 COMPLETE (phase26 · 20/20) |
| 15 | 최종 기록·판정 | FIG-36/37 | R-FINAL-REPORT | FIG-36 COMPLETE (`fig-36-native-owned-final-integration-2026-11-26.md`). 공개 GO는 FIG-37/승인 |

---

## 3. 잔여 항목 상세

### 3.1 Baseline · Preservation · Matrix

| id | source | status | blocks-what | parallel-ok? | next verifiable unit |
|---|---|---|---|---|---|
| R-BASE-FIG00 | fig-00 · phase00-live-baseline-2026-11-26 | COMPLETE | — | yes | HEAD `47c1d21` 실측 반영됨. Sidecar PID·schema fingerprint만 보강 여지 |
| R-PRESERVE-FIG01 | fig-01 | UNVERIFIED (다수 표면) / PARTIAL (Shell Control·Browser 별칭) | Gate D GO | yes (관측만) | 표면별 스크린샷·계약 재실행 표 → VERIFIED/REGRESSION 승격 |
| R-MATRIX-FIG02 | fig-02 | PARTIAL | Gate E 완주 | partial | 승인 없는 Unit A 재실행. 120B는 승인 게이트 |
| R-FIG-03 | fig-03-owned-vs-reference-min-repro | COMPLETE | — | yes | hello_match·shell_match true (`.tmp/fig-03/evidence.json`) |

### 3.2 Runtime repair (FIG-04…10 / FGC 1–3단)

| id | source | status | blocks-what | parallel-ok? | next verifiable unit |
|---|---|---|---|---|---|
| R-OBS-FIG04 | wave1-progress | PARTIAL | 실패 원인 추적 품질 | yes | 라이브 턴에서 TOOL_RESULT/TOOL_CALL 한 줄이 agent.log에 남는지 |
| R-SHELL-CONTRACT | fig-00 · FGC · gpt-oss · wave1 | COMPLETE (계약) | — | — | `_check_tool_contract` · `_check_speak_surface_shell` exit 0 유지 |
| R-SHELL-LIVE | FGC · phase04-shell-live-retest | COMPLETE (실행 경로) | — | — | 실배열·bash-list coerce + 모델 턴 exit 0. 비서 마커 인용 soft FAIL 분리 |
| R-SHELL-ASSIST | phase20-shell-assist-nudge | COMPLETE (계약) | 라이브 마커 인용 재판정 | yes | Host `ShellAssistNudge` + `_check_shell_assist_nudge` exit 0 |
| R-BROWSER-LIVE | FGC · gpt-oss | PARTIAL | 13전수 Browser 줄 | yes | needs_reapproval·지연·Wiki→Browser 연속 라이브 |
| R-SCHEMA-FIG06 | wave1-progress | PARTIAL | 모델 도구 선택 품질 | yes | terminal/process_manage/ide.edit 설명 계약 재검. 라이브 pick UNVERIFIED |
| R-WS-FIG07 | wave1-progress | COMPLETE (체크) | — | — | `_check_workspace_environment` exit 0 유지 |
| R-PLAN-FIG08 | wave1-progress · FGC | PARTIAL | process 승인 무결성 | yes | plan.env→start(env=) 라이브. timeout/environment_id raw UNVERIFIED |
| R-NAT-FIG09 | phase17-gate-b-negative | COMPLETE (계약) | 라이브 TOOL_RESULT만 잔여 | yes | `_check_native_tool_hermes_disabled` gate_b=unregistered,inactive,approval_refuse |
| R-CTX-FIG10 | ACF · gpt-oss | PARTIAL | 도구 루프 진입 | yes | num_ctx 64000 미만 거절 경로 계약. 프로파일 16384 회귀 방지 |
| R-UV-PROBE | wave1-progress · phase04 | COMPLETE | — | — | `_check_uv_probe_boost_no_editable` → 현재 API 정렬. exit 0 (`phase04-uv-probe-stamp-fix-2026-11-26.md`) |
| R-META-HOST | FGC 1단 | COMPLETE | — | — | `_check_execution_context` 등 exit 0 유지 |
| R-PROC-FINALIZE | FGC 2단 | COMPLETE | — | — | finalize→consume→start 계약 유지 |

### 3.3 Product repair · FPR · Gates A–E

| id | source | status | blocks-what | parallel-ok? | next verifiable unit |
|---|---|---|---|---|---|
| R-FPR14-CODE | fpr-14 | PARTIAL (CONDITIONAL) | 완전 GO | — | 코드 잔여 닫힘 주장 유지. 라이브는 아래 |
| R-FPR11-IDE | fpr-14 | UNVERIFIED | IDE Hotfix GO | yes | LiveOutputRing·IDE mirror·dirty patch 실측 |
| R-FPR-HUD | fpr-14 · FGC | OPEN | 승인 UX 완주 | yes | clear_history·attachment·scaffold confirm_required HUD |
| R-SIDECAR-HANG | fpr-14 | UNVERIFIED | 착지 회귀 | yes | `_check_sidecar_done_landing` hang-after-Turn-ended |
| R-EMAIL-COMPOSE | gpt-oss · ACF · fpr-14 | PARTIAL / REGRESSION 후보 | 시나리오 13 | yes | 모델 경로 compose dialog. Control 프리필은 ok |
| R-GATE-A | wave1 · FGC | PARTIAL | Gate A GO | yes | iris_shell/file_patch/execution_context/chat_landing ok 유지 + 잔여 채움 |
| R-GATE-B | phase17-gate-b-negative | COMPLETE (계약) | Security 공개 릴리스 라이브 증거 | yes | 미등록·Hermes 원본·confirm 단독 거절 exit 0. 라이브 턴 UNVERIFIED |
| R-GATE-C | ACF · FGC | OPEN/PARTIAL | 모델 성능 게이트 | no (유료/승인) | 승인 범위 안 120B/로컬 핵심 작업 표 |
| R-GATE-D | fig-01 | UNVERIFIED | Product Preservation GO | yes | GUI 전수 표. 손대는 수정은 REGRESSION 증거 있는 표면만 |
| R-GATE-E | fig-02 · ACF-11 | PARTIAL | Engine Parity GO | partial | 동일 모델 HELLO 이상 도구 패리티. 라이브 홈 쓰기 금지 |
| R-13FPR-GUI | FGC · phase18 · phase25 · phase26 | COMPLETE | — | yes | `--include-live` 20/20. l01=`_check_owned_live_hello` · l04=`_check_owned_live_shell`. `phase26-fpr13-owned-live-unblock-2026-11-26.md` |
| R-RUNNER-FIG19 | phase18-fpr13-runner | COMPLETE | — | yes | `python -m iris.system._check_fpr13_runner --contracts-only` |

### 3.4 Owned Core · Cutover · Legacy

| id | source | status | blocks-what | parallel-ok? | next verifiable unit |
|---|---|---|---|---|---|
| R-OWNED-INSTALL | ACF-01…04 · FIG-25/26 · phase16-owned-core-011 | COMPLETE (격리 설치) | 배포 번들·live cutover | yes | `.tmp/owned-core-011` version_match·import_ok |
| R-OWNED-ROLLBACK | phase21-owned-rollback-proof | COMPLETE | — | yes | `.tmp/owned-rollback-proof` rollback_ok·live_untouched |
| R-OWNED-PARITY | ACF-11/12 · fig-02 · fig-03 | PARTIAL | Gate E · 공개 cutover | partial | hello+shell PASS. 도구 전수·Owned GUI 턴 1건 남음 |
| R-E-FALLBACK | phase23-hermes-fallback-off | COMPLETE | — | yes | owned > hermes when no selection. hermes=recovery |
| R-GUI-SMOKE-POST | phase22 후 | OPEN | 공개 전 최소 스모크 | no (live GUI) | Iris 1 + Owned active 한 턴 assistant 착지 |
| R-ACF05 | ACF-05 · fig-29 | COMPLETE (차단) | — | — | hermes_disabled 회귀 잠금 유지 |
| R-ACF06 | ACF-06 | PARTIAL | Gateway 정리 | yes | 진단·opt-in 경로 호출자 목록화 (삭제 금지) |
| R-ACF07 | ACF-07 | PARTIAL | CLI 정리 | yes | 호환 shim 호출자 → 이전 계획만 |
| R-ACF08 | ACF-08 | PARTIAL | MCP 정책 | yes | 기본 sync에서 MCP 점검 제외 계약 재검 |
| R-ACF09 | ACF-09 | COMPLETE (분류) | — | yes | 비활성 도구 제품 등록 0 유지 |
| R-ASSETS-ABSORB | ACF 남은 자산 | OPEN / UNVERIFIED | Core 흡수 완주 | yes | Conversation Loop 등 분기별 실행 증거 (개발 가능) |
| R-HERMES-AUDIT | fig-29 · FINAL EXEC 재감사 | COMPLETE | — | — | C dead install.ps1(phase19). E fallback COMPLETE(phase23) |
| R-PHYS-DELETE | fig-29 · ACF-13 · FIG-33 | **KEEP** | 물리 삭제 | no | 동등성+회귀 전수 전 삭제 금지 |
| R-MIGRATE-FALSE | FGC · ACF-10 · FIG-27 · fig-00 | **KEEP** (공개/전체 사용자) | 전체 사용자 승격 · 릴리스 | no | 공개 `legacy_migration_approved` 승격은 별도 승인. 개발 cutover는 FINAL EXEC |
| R-CUTOVER-PROOF | phase22-dev-owned-cutover | COMPLETE (개발) / KEEP (공개) | 공개 전환만 KEEP | partial | live active=`iris-agent.slot-e38f3ea761714c36` previous=`hermes-agent` |
| R-FINAL-REPORT | FIG-36/37 · ACF-15 | COMPLETE (FIG-36) / OPEN (공개 GO) | 공개 릴리스 판정 | yes | `fig-36-native-owned-final-integration-2026-11-26.md`. FIG-37/공개 GO는 별 승인 |

### 3.5 확인한 사실 (교차 요약)

| 사실 | 출처 | 라벨 |
|---|---|---|
| 실 GUI 엔진 (cutover 전) = Reference `hermes-agent` | fig-00 | measured (당시) |
| 실 개발 홈 active = `iris-agent.slot-e38f3ea761714c36` · previous=`hermes-agent` | phase22 · `.tmp/dev-cutover/evidence.json` | measured |
| 격리 Owned 0.1.1 version_match·import_ok | `.tmp/owned-core-011/evidence.json` | measured |
| FIG-03 hello_match·shell_match true | `.tmp/fig-03/evidence.json` | measured |
| 격리 rollback_ok·live_untouched | `.tmp/owned-rollback-proof/evidence.json` | measured |
| Gate B 계약 · FPR13 계약 16 · ShellAssistNudge | phase17–20 | measured |
| Dead Hermes install.ps1 경로 제거 | phase19 | measured |
| `legacy_migration_approved=false` · hermes 미삭제 | fig-00 · phase22 | measured |
| FGC/ACF 공개 판정 NO-GO | FGC · ACF · FIG-36 | measured |
| 13+FPR GUI 라이브 4행 미완 | FPR-14 · phase18 | measured |
| FPR-14 판정 CONDITIONAL | fpr-14 | measured |

---

## 4. 비가역 게이트 KEEP (명시)

아래는 Development Gate에서도 **열지 않는다**. NO-GO가 가리키는 진짜 막힘이다.

| KEEP id | 내용 | 해제 조건 (아직 미충족) |
|---|---|---|
| R-MIGRATE-FALSE | 전체 사용자 대상 `legacy_migration_approved` 공개 승격 | Product Stability + Engine Parity GO + 별도 사용자 승인 |
| R-DEV-CUTOVER | 개발자 라이브 홈 Owned 전환 | **실행됨** (phase22). previous=hermes 보존. 공개와 무관 |
| R-CUTOVER-PROOF (공개) | 전체 사용자 엔진 전환 공표 | 공개 릴리스 게이트 이후 |
| R-PHYS-DELETE | Hermes/vendor/Reference 물리 삭제 | FIG-33 조건 (무호출자 · 무동적 import · 회귀 전수) |
| R-USER-DATA | Agent Home 사용자 파일·DB·자격 증명 삭제/이동 | 별도 승인 |
| R-GIT-REMOTE | commit / push / 배포 승격 | 사용자 요청 |
| R-PAID-EXPAND | 유료·상위 모델 행렬 확대 | 사용자 승인 (FIG-02 Blocked-on-approval) |

Reference Core는 **비교·복구 전용**으로 KEEP한다. 미래 정본으로 승격하지 않는다.

---

## 5. 조치 — 다음 검증 단위 (구현 순서)

닫힘: R-SHELL-LIVE · R-UV-PROBE · R-OWNED-INSTALL · R-OWNED-ROLLBACK · R-FIG-03 · R-GATE-B(계약) · R-RUNNER-FIG19 · R-SHELL-ASSIST · R-CUTOVER-PROOF(개발) · R-E-FALLBACK · R-GUI-SMOKE-POST · R-13FPR-GUI · FIG-36.

1. **R-OWNED-PARITY** — 도구 전수·GUI 동등 (공개 전).
2. **R-MIGRATE-FALSE** — 위 GO + 사용자 승인 후에만 공개 승격 검토.

Wave 2 청구·물리 삭제·공개 migration은 KEEP가 풀리기 전 착수하지 않는다. Gate D 인벤토리·R-ASSETS-ABSORB는 병렬 가능.
