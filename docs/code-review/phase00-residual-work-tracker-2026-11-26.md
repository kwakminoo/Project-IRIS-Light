# PHASE 00 Residual Work Tracker — IRIS Independent Native Agent

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE00-RWT-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | FIG-00/01/02/29 · FGC · ACF · FPR-14 · GPT-OSS ACF GUI · Wave1 progress |
| 대상 | Hermes 전면 흡수 후 IRIS 독립 Native Agent 잔여 작업 |
| 목적 | 게이트 문서 상태를 한 표로 고정. Development Gate 정책 아래 진행 가능 단위를 분리 |

## Development Gate 정책 (이번 트래커 권위)

| 규칙 | 적용 |
|---|---|
| 기존 **NO-GO** | **공개 릴리스**와 **비가역 사용자 환경 변경**만 막는다 |
| 개발·통합 | NO-GO여도 **계속**한다 |
| Reference Core | 비교·복구 전용. **미래 정본 아님** |
| 금지 (KEEP) | commit/push · 사용자 데이터 삭제 · `legacy_migration_approved` 승격 · 라이브 홈 cutover |

상태 라벨: `COMPLETE` · `PARTIAL` · `REGRESSION` · `UNVERIFIED` · `OPEN` · `KEEP` (비가역 게이트 유지).

출처 문서는 다시 쓰지 않았다. 상태만 추출·재분류했다.

---

## 1. 결론

**공개 릴리스는 여전히 NO-GO다.** 개발은 막히지 않는다. P0 모델 `shell.run` 실행 경로(격리 실모델)는 **COMPLETE**. 릴리스를 막는 남은 P0는 13+FPR GUI 전수·Owned 도구 동등·Gate A 잔여다. 비서 본문 마커 미인용은 soft로 분리한다.

| 우선 | ID | 상태 | 한 줄 |
|---|---|---|---|
| P0 | R-SHELL-LIVE | COMPLETE | 격리 `gpt-oss:20b` 턴 exit 0 · TOOL_RESULT ok (`phase04-shell-live-retest`) |
| P0 | R-GATE-A-REST | PARTIAL | Gate A 계약 다수 ok. R-UV-PROBE COMPLETE. runner·잔여 표면 남음 |
| P0 | R-13FPR-GUI | OPEN | 13+FPR 라이브 전수·시나리오 러너 미완 |
| P0 | R-OWNED-PARITY | PARTIAL | HELLO/Unit A PASS. 도구·GUI 동등·120B 승인 대기 |
| P1 | R-HERMES-RETIRE | PARTIAL | FIG-29 감사 COMPLETE(REMOVE 없음). 물리 삭제 KEEP |
| P1 | R-SURFACE-UNVER | UNVERIFIED | FIG-01 다수 표면 EXISTING BUT UNVERIFIED |
| KEEP | R-MIGRATE-FALSE | KEEP | `legacy_migration_approved=false` · 사용자 홈 전환 금지 |

**병렬 가능 (서로 쓰기 충돌 없음)**

1. R-13FPR-GUI / 시나리오 러너
2. R-GATE-A-REST 잔여 (runner·기타 Gate A 표면; R-UV-PROBE·R-SHELL-LIVE 닫힘)
3. R-FIG-03 결정론 shell/process 최소 재현
4. R-FIG-09 / Gate B negative 계약
5. R-SURFACE-UNVER 중 촬영·표만 하는 Gate D 인벤토리 (코드 변경 없음)

**직렬 필수**

- R-13FPR-GUI → R-OWNED-PARITY 완주 → (승인 후) R-CUTOVER-PROOF
- R-HERMES-RETIRE 물리 삭제(FIG-33) → 위 동등성 GO 이후만
- R-MIGRATE-FALSE 승격 → cutover 증거 + 사용자 승인 이후만

원칙: **Sequence Verifiable Units** (단위마다 검사 후 다음), **Outcome-Oriented Execution** (릴리스 NO-GO를 개발 정지로 쓰지 않음).

---

## 2. PHASE 00–15 ↔ 잔여 매핑

Full Absorption 골격은 ACF-00…15 (`iris-agent-wave1-finalization-gate.md`)다.  
Wave 1 Final Integration FIG 트랙(PHASE 00–07 / FIG-00…37)은 같은 목표의 실행 단위로 옆에 붙인다.

| PHASE | Full Absorption (ACF) | Wave1 FIG 트랙 | 잔여 ID (요약) | 단계 상태 |
|---|---|---|---|---|
| 00 | 엔진·경로 인벤토리 | FIG-00 Baseline | R-BASE-FIG00 | COMPLETE (`phase00-live-baseline`, HEAD `47c1d21`). GUI 미기동으로 PID·fingerprint PARTIAL/UNVERIFIED |
| 01 | 패키지·Manifest·lock | FIG-01 Preservation | R-PRESERVE-FIG01 | PARTIAL / 표면 UNVERIFIED |
| 02 | Clean install (Windows) | FIG-02 Matrix prep | R-MATRIX-FIG02 | PARTIAL (Unit A+HELLO). 120B OPEN(승인) |
| 03 | Slot·selection·rollback | FIG-03 Min repro | R-FIG-03 | OPEN |
| 04 | Wizard/Setup·업데이트 경로 | FIG-04…10 Runtime repair | R-OBS-FIG04, R-SHELL-*, R-SCHEMA-FIG06, R-WS-FIG07, R-PLAN-FIG08, R-NAT-FIG09, R-CTX-FIG10 | 계약 PARTIAL. 라이브 잔여 |
| 05 | Native dispatch 차단 | (FIG-09 포함) | R-NAT-FIG09, R-ACF05 | COMPLETE(차단). 원본 파일 삭제 KEEP |
| 06 | Sidecar vs Gateway 분리 | FIG-29…33 Legacy | R-HERMES-*, R-ACF06 | PARTIAL. 물리 삭제 KEEP |
| 07 | 이름·CLI·overlay bake | FIG-31 CLI cleanup | R-ACF07 | PARTIAL |
| 08 | MCP/SOUL/Mobile 보존 | FIG-32 Integrations | R-ACF08 | PARTIAL |
| 09 | 자산 분류·비활성 도구 | FIG-32 | R-ACF09, R-ASSETS | COMPLETE(분류). 흡수 미검증 OPEN |
| 10 | 기존 사용자 마이그레이션 | FIG-27 | R-MIGRATE-FALSE | **KEEP false** |
| 11 | Reference/Owned 동등 | FIG-02/03/22/24 · Gate C/E | R-OWNED-PARITY, R-GATE-C, R-GATE-E | PARTIAL |
| 12 | Hermes checkout 없는 Owned 실행 | FIG-25/26/28 | R-OWNED-INSTALL, R-CUTOVER-PROOF | PARTIAL / cutover KEEP |
| 13 | Hermes 물리 삭제 게이트 | FIG-33 | R-PHYS-DELETE | **KEEP** (조건 미충족) |
| 14 | 증거·회귀 묶음 | FIG-11…24 · FPR · Gate A–D | R-13FPR-GUI, R-GATE-*, R-FPR-* | PARTIAL / OPEN |
| 15 | 최종 기록·판정 | FIG-36/37 | R-FINAL-REPORT | OPEN (FIG-36 미작성). ACF-15 문서 COMPLETE |

---

## 3. 잔여 항목 상세

### 3.1 Baseline · Preservation · Matrix

| id | source | status | blocks-what | parallel-ok? | next verifiable unit |
|---|---|---|---|---|---|
| R-BASE-FIG00 | fig-00 · phase00-live-baseline-2026-11-26 | COMPLETE | — | yes | HEAD `47c1d21` 실측 반영됨. Sidecar PID·schema fingerprint만 보강 여지 |
| R-PRESERVE-FIG01 | fig-01 | UNVERIFIED (다수 표면) / PARTIAL (Shell Control·Browser 별칭) | Gate D GO | yes (관측만) | 표면별 스크린샷·계약 재실행 표 → VERIFIED/REGRESSION 승격 |
| R-MATRIX-FIG02 | fig-02 | PARTIAL | Gate E 완주 | partial | 승인 없는 Unit A 재실행. 120B는 승인 게이트 |
| R-FIG-03 | wave1-progress (next) | OPEN | Gate C/E 최소 증거 | yes | Reference+Owned 동일 조건. 무도구 대화 + Home terminal→shell 1회 |

### 3.2 Runtime repair (FIG-04…10 / FGC 1–3단)

| id | source | status | blocks-what | parallel-ok? | next verifiable unit |
|---|---|---|---|---|---|
| R-OBS-FIG04 | wave1-progress | PARTIAL | 실패 원인 추적 품질 | yes | 라이브 턴에서 TOOL_RESULT/TOOL_CALL 한 줄이 agent.log에 남는지 |
| R-SHELL-CONTRACT | fig-00 · FGC · gpt-oss · wave1 | COMPLETE (계약) | — | — | `_check_tool_contract` · `_check_speak_surface_shell` exit 0 유지 |
| R-SHELL-LIVE | FGC · phase04-shell-live-retest | COMPLETE (실행 경로) | — | — | 실배열·bash-list coerce + 모델 턴 exit 0. 비서 마커 인용 soft FAIL 분리 |
| R-BROWSER-LIVE | FGC · gpt-oss | PARTIAL | 13전수 Browser 줄 | yes | needs_reapproval·지연·Wiki→Browser 연속 라이브 |
| R-SCHEMA-FIG06 | wave1-progress | PARTIAL | 모델 도구 선택 품질 | yes | terminal/process_manage/ide.edit 설명 계약 재검. 라이브 pick UNVERIFIED |
| R-WS-FIG07 | wave1-progress | COMPLETE (체크) | — | — | `_check_workspace_environment` exit 0 유지 |
| R-PLAN-FIG08 | wave1-progress · FGC | PARTIAL | process 승인 무결성 | yes | plan.env→start(env=) 라이브. timeout/environment_id raw UNVERIFIED |
| R-NAT-FIG09 | wave1-progress (next) | OPEN/PARTIAL | Gate B | yes | hermes_disabled 재검 + 미등록/비활성 툴 negative |
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
| R-GATE-B | wave1 (next) | OPEN | Security 릴리스 | yes | negative: 미등록 툴 · Hermes 원본 · 승인 우회 |
| R-GATE-C | ACF · FGC | OPEN/PARTIAL | 모델 성능 게이트 | no (유료/승인) | 승인 범위 안 120B/로컬 핵심 작업 표 |
| R-GATE-D | fig-01 | UNVERIFIED | Product Preservation GO | yes | GUI 전수 표. 손대는 수정은 REGRESSION 증거 있는 표면만 |
| R-GATE-E | fig-02 · ACF-11 | PARTIAL | Engine Parity GO | partial | 동일 모델 HELLO 이상 도구 패리티. 라이브 홈 쓰기 금지 |
| R-13FPR-GUI | FGC · fpr-14 · gpt-oss · ACF | OPEN | Wave1 릴리스 GO | after shell live | 격리 profile 시나리오 러너 + Reference 동일 조건 표 |
| R-RUNNER-FIG19 | FGC 차용 · wave1 | OPEN | 13전수 반복 | yes | verify-iris/_check_* 묶음 최소 러너 |

### 3.4 Owned Core · Cutover · Legacy

| id | source | status | blocks-what | parallel-ok? | next verifiable unit |
|---|---|---|---|---|---|
| R-OWNED-INSTALL | ACF-01…04 · FIG-25/26 · phase08-owned-isolated-evidence | PARTIAL | 배포 번들 GO | yes | hermes-less import·cheap 체크 PASS. fixture `0.1.0`↔vendor `0.1.1` drift 해소 + install/update/rollback 재실행 |
| R-OWNED-PARITY | ACF-11/12 · fig-02 | PARTIAL | Gate E · cutover | partial | 도구 실패 없는 Owned GUI 턴 1건 (fixture는 HELLO/Unit A만) |
| R-ACF05 | ACF-05 · fig-29 | COMPLETE (차단) | — | — | hermes_disabled 회귀 잠금 유지 |
| R-ACF06 | ACF-06 | PARTIAL | Gateway 정리 | yes | 진단·opt-in 경로 호출자 목록화 (삭제 금지) |
| R-ACF07 | ACF-07 | PARTIAL | CLI 정리 | yes | 호환 shim 호출자 → 이전 계획만 |
| R-ACF08 | ACF-08 | PARTIAL | MCP 정책 | yes | 기본 sync에서 MCP 점검 제외 계약 재검 |
| R-ACF09 | ACF-09 | COMPLETE (분류) | — | yes | 비활성 도구 제품 등록 0 유지 |
| R-ASSETS-ABSORB | ACF 남은 자산 | OPEN / UNVERIFIED | Core 흡수 완주 | yes | Conversation Loop 등 분기별 실행 증거 (개발 가능) |
| R-HERMES-AUDIT | fig-29 | COMPLETE | — | — | REMOVE 후보 없음 유지. 재감사는 호출자 변경 시 |
| R-PHYS-DELETE | fig-29 · ACF-13 · FIG-33 | **KEEP** | 물리 삭제 | no | 동등성+회귀 전수 전 삭제 금지 |
| R-MIGRATE-FALSE | FGC · ACF-10 · FIG-27 · fig-00 | **KEEP** | 사용자 홈 전환 · 릴리스 | no | `legacy_migration_approved` **false 유지** |
| R-CUTOVER-PROOF | ACF-12 · FIG-28 · FGC 4단 | **KEEP** / OPEN | 공개 전환 | no | 동등성 GO + 테스트 홈 복제 전환·롤백 후에만 |
| R-FINAL-REPORT | FIG-36/37 · ACF-15 | OPEN | 영역별 최종 판정 문서 | yes (작성) | `iris-wave1-final-integration-release-gate.md` 초안. 릴리스 GO는 별 승인 |

### 3.5 확인한 사실 (교차 요약)

| 사실 | 출처 | 라벨 |
|---|---|---|
| 실 GUI 엔진 = Reference `hermes-agent` | fig-00 | measured (당시) |
| Owned = vendor만. live `iris-agent` 없음 | fig-00 | measured |
| `legacy_migration_approved=false` | fig-00 · FGC · ACF | measured |
| FGC/ACF 공개 판정 NO-GO | FGC · ACF · gpt-oss | measured |
| 모델 browser `url` 별칭 후 ok:true | gpt-oss · FGC | measured |
| 모델 shell argv bash 리스트 → exit 1 | gpt-oss | measured |
| Control shell 동일 마커 exit 0 | gpt-oss · FGC | measured |
| FIG-05/04/07/29 계약 또는 감사 닫힘 | wave1-progress | measured |
| `_check_uv_probe_boost_no_editable` FAIL → exit 0 (stamp API 정렬) | phase04 | measured |
| 13+FPR GUI 전수 미완 | FPR-14 · FGC · ACF | measured |
| FPR-14 판정 CONDITIONAL | fpr-14 | measured |

---

## 4. 비가역 게이트 KEEP (명시)

아래는 Development Gate에서도 **열지 않는다**. NO-GO가 가리키는 진짜 막힘이다.

| KEEP id | 내용 | 해제 조건 (아직 미충족) |
|---|---|---|
| R-MIGRATE-FALSE | `SOURCE_MANIFEST.legacy_migration_approved` false | Product Stability + Engine Parity GO + 사용자 승인 |
| R-CUTOVER-PROOF | 라이브 `~/.iris-light/agent` 엔진 전환·선택 파일 쓰기 | 테스트 홈 전환·롤백 성공 증거 후 별도 승인 |
| R-PHYS-DELETE | Hermes/vendor/Reference 물리 삭제 | FIG-33 조건 (무호출자 · 무동적 import · 회귀 전수) |
| R-USER-DATA | Agent Home 사용자 파일·DB·자격 증명 삭제/이동 | 별도 승인 |
| R-GIT-REMOTE | commit / push / 배포 승격 | 사용자 요청 |
| R-PAID-EXPAND | 유료·상위 모델 행렬 확대 | 사용자 승인 (FIG-02 Blocked-on-approval) |

Reference Core는 **비교·복구 전용**으로 KEEP한다. 미래 정본으로 승격하지 않는다.

---

## 5. 조치 — 다음 검증 단위 5개 (구현 순서)

닫힘: R-SHELL-LIVE · R-UV-PROBE.

1. **R-FIG-03** — Reference+Owned(격리) 최소 재현. 무도구 HELLO + terminal→shell 1회.
2. **R-NAT-FIG09 / R-GATE-B** — hermes_disabled + 미등록/비활성 툴 negative `_check_*` 묶음 녹색.
3. **R-RUNNER-FIG19 → R-13FPR-GUI** — 기존 `_check_*`/verify-iris를 묶는 최소 시나리오 러너 후 표 채움.
4. **R-OWNED-INSTALL drift** — fixture `0.1.0` → vendor `0.1.1` 정렬 (격리만).
5. **R-SHELL-ASSIST soft** — 도구 성공 후 비서 마커 인용 (Product Stability soft).

이후(직렬): Gate D 표면 승격 → Owned 도구 패리티 → (승인) cutover 시험.  
Wave 2 제품·물리 삭제·migration 승격은 KEEP가 풀리기 전 착수하지 않는다. 개발용 Core 흡수(R-ASSETS-ABSORB)는 병렬 가능.
