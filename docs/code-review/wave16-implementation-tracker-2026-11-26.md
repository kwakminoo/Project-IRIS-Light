# Wave 1.6 Implementation Tracker

| 항목 | 내용 |
|---|---|
| 문서 번호 | W16-TRACK-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | Codex `Harden IRIS native independence` · brief NIP-00…13 |
| 대상 | Working tree on `main` @ `029c1ceef289d78f7fb4a66271d686c95cd20aba` |
| 목적 | Wave 1.6 실측 상태를 고정하고 Wave 2 Entry만 판정한다 |

## 1. 결론

Owned Core·NIP-01/02 핫패스·NIP-12(57/57)·FPR13 contracts(17/17)·L3 live(hello+shell)·L5/L6·vibe_smoke 9/9·제품 Control(browser/shell/email.compose_draft)는 green이다. NIP-09는 PARTIAL(로컬 멀티툴 매트릭스 미완·유료 OPEN). FPR13 `ide_product_control`만 `--product-home` 없으면 UNVERIFIED. gateway ISOLATE. `legacy_migration_approved=false`.

**Wave 2 Entry:** 개발 **CONDITIONAL GO** / 공개·마이그레이션 **NO-GO**.

## 2. Owned Core (실측)

| 항목 | 값 | 증거 |
|---|---|---|
| Vendor + active | `0.1.2+iris.a382af23` | `vendor/iris-agent-core/SOURCE_MANIFEST.json` · `~\.iris-light\agent\iris-agent.slot-272facc0f5fd4b6f\SOURCE_MANIFEST.json` |
| Active slot | `iris-agent.slot-272facc0f5fd4b6f` | NIP-01/09 closure · slot manifest |
| Update / rollback / reupdate | verified | FPR13 `installer_lifecycle` PASS · lifecycle evidence under `.tmp/wave16-lifecycle/` / `.tmp/fpr13/logs/installer_lifecycle.log` |
| HELLO | PASS | FPR13 `l01_general_chat` · NIP-09 `1_general_chat` |
| Hermes on import path | no | `nip01-02-closure-evidence-2026-11-26.md` |
| `legacy_migration_approved` | **false** | SOURCE_MANIFEST (vendor + slot) |

## 3. NIP 상태 (`029c1ce`)

| Phase | 상태 | 비고 / 증거 |
|---|---|---|
| NIP-00 Baseline | DONE | HEAD=`029c1ce` |
| NIP-01 Engine Independence | DONE (핫패스) | `docs/code-review/nip01-02-closure-evidence-2026-11-26.md` PASS |
| NIP-02 Residual/Gateway | DONE (핫패스) / 모듈 **ISOLATE** | 동 문서. spawn 0. R-ASSETS-ABSORB 전분기 OPEN |
| NIP-03 Runtime Hardening | 계약 DONE | stall·cancel·idle·sidecar 계열 유지 |
| NIP-04 Tool grounding | DONE (L3) | FPR13 `l04` PASS · NIP-09 matrix shell auto PASS (`_check_owned_live_shell --auto`는 fixture 플레이크 잔여) |
| NIP-05 Tool security | DONE (계약) | contracts + approval 경로 |
| NIP-06 IDE | 계약 DONE / product L4 UNVERIFIED | vibe_smoke 9/9 PASS. FPR13 `ide_product_control` needs `--product-home` |
| NIP-07 Product features | DONE | vibe_smoke · L5 · Control browser/shell/email.compose_draft (`sent:false`) |
| NIP-08 E2E infra | DONE (flag 실측) / L4 UNVERIFIED | contracts+live+gui+lifecycle PASS. L4만 product-home 미배선 |
| NIP-09 Model quality | **PARTIAL** | auto/single/shell PASS · multi-tool PARTIAL · 나머지 PARTIAL/OPEN · `docs/code-review/nip09-model-quality-closure-2026-11-26.md` |
| NIP-10 Lifecycle | PASS (격리) | FPR13 `installer_lifecycle` PASS. 제품 홈 재설치 KEEP |
| NIP-11 Hygiene | DONE | branding·no-console·gitignore 계약 |
| NIP-12 Full regression | **PASS** (57/57) | `.tmp/nip12-regression/results.json` · `docs/code-review/nip12-full-regression-2026-11-26.md` |
| NIP-13 Wave 2 Entry | **CONDITIONAL GO (dev) / NO-GO (public)** | 아래 §5 |

## 4. FPR13 (latest `.tmp/fpr13/results.json`)

| Layer | Status | Detail |
|---|---|---|
| L2 contracts | **17/17 PASS** | c01–c14 + fpr_* roster/runtime/transcript |
| L3 live | hello **PASS** · shell **PASS** | `--include-live` 재실측. l04 evidence attempt=1 after harden |
| L4 product | **UNVERIFIED** | `ide_product_control` — needs `--product-home` (vibe_smoke로 제품 IDE는 별도 PASS) |
| L5 GUI | **PASS** | `wiki_browser_gui` · `process_approval_gui` (라이브 IRIS와 동시 실행 시 singleton 충돌 주의) |
| L6 lifecycle | **PASS** | `installer_lifecycle` |
| Combined | live 21 pass / 0 fail (L4·L5·L6 skip when flag absent) · gui+lifecycle 20 pass / 0 fail | `.tmp/fpr13/results.json` 최신 런은 flag 조합에 따라 unverified 행 존재. **FAIL 0** |

제품 vibe: **9/9 PASS**. Control smoke: browser.navigate ok · shell.run ok · email.compose_draft `sent:false` (`.tmp/wave16-product-gui-control.json`).

## 5. Wave 2 Entry (NIP-13)

| 조건 | 상태 | 판정 |
|---|---|---|
| Owned Core + HELLO + update/rollback | PASS | 개발 허용 근거 |
| NIP-01/02 핫패스 | PASS · gateway ISOLATE | 개발 허용 근거 |
| NIP-12 contracts | 57/57 PASS | 개발 허용 근거 |
| FPR13 contracts + L5/L6 | PASS | 개발 허용 근거 |
| NIP-09 quality matrix | PARTIAL (multi-tool/file/IDE PARTIAL · paid OPEN) | **공개 차단** · 개발 GO의 주요 잔여 |
| FPR13 L4 ide_product_control | UNVERIFIED | vibe_smoke로 완화. 러너 flag 배선은 잔여 |
| `legacy_migration_approved` | false | **승격 금지** |
| 공개 Production / migration | — | **NO-GO** |

**Verdict:** Wave 2 Entry = **CONDITIONAL GO (development only)** / **public NO-GO**.  
핵심 독립성·회귀·FPR13 실행 계층은 통과. NIP-09 멀티툴 품질·공개 cutover는 미완이라 공개 GO는 아니다. Wave 2 기능 착수는 하지 않는다.

## 6. KEEP

- `legacy_migration_approved=false`
- hermes 물리 삭제 금지
- 요청 없는 commit/push
- 사용자 데이터 영구 삭제 금지
- Wave 2 feature 시작 금지 (이번 문서 작업 범위)

## 7. 조치

1. 공개 GO·migration 승격·commit/push·Wave 2 기능은 요청 전까지 하지 않는다.
2. 다음 가역 단위(원하면): FPR13 L4 `--product-home` 배선, NIP-09 multi-tool·file 완주, streaming/cancel 제품 GUI 수동 표.
3. 본 트래커 HEAD는 `029c1ce`로 고정한다.
