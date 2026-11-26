# Wave 1.6 Implementation Tracker

| 항목 | 내용 |
|---|---|
| 문서 번호 | W16-TRACK-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | Codex `Harden IRIS native independence` · brief NIP-00…13 |
| 대상 | Working tree on `main` @ `44df2f2` + dirty Wave 1.6 edits |
| 목적 | Codex 한도 끊김 이후 이어서 구현·검증할 단위 고정 |

## 1. 결론

이번 재개로 NIP-02~08·11 핵심은 green이다. NIP-09는 PARTIAL(로컬 HELLO·grounding·짧은 계약 PASS, 멀티모델/외부 live OPEN). NIP-12 OPEN · NIP-13 KEEP → **Wave 2 진입 불가**. gateway 모듈 ISOLATE.

## 2. Codex 트레일 (권위)

| 시각/메시지 | 내용 | 판정 |
|---|---|---|
| 시작 | Ponytail으로 Wave 1.6 brief 읽고 stage 진행 | — |
| 중간 | Owned 선택 이미 있음. corrupt/missing selection 수용 과다 → 선택·복구 강화 | DONE (코드+`agent_runtime` self-check) |
| 중간 | engine/installer 포커스 체크 PASS. 격리 lifecycle uv 설치 시작 | DONE |
| 중간 | Gateway fallback을 routine/summary에서 발견. Graphify 후 제거 예정 | OPEN (끊김) |
| 마지막 사용자 인용 | clean install `gpt-oss:20b` 턴 OK. staged update exact-response 실패 → prior slot 유지. process approval env/timeout fingerprint 수정 | PARTIAL→lifecycle 증거는 이후 완주 |
| IDE/Validation 형제 | usage limit 로 FINAL_ANSWER 실패 | OPEN |

세션 id: `01a216a6-b0b0-7590-ab18-3ac0012d1fc4`

## 3. 상속 증거 (재실행·실측)

| 주장 | 증거 | 상태 |
|---|---|---|
| Owned 선택 무결성 | `selected_owned_engine` integrity+venv 검사. hermes 자동 선택 제거 | PASS (`python -m iris.infrastructure.agent_runtime`) |
| Live selection | active=`iris-agent.slot-e38f3ea761714c36`, previous=`hermes-agent` | PASS (실측) |
| Process approval env/timeout | `FinalizedStartPlan.environment_id`/`timeout_s` fingerprint | PASS (`_check_process_manage` · `_check_request_approval` · `_check_run_approval`) |
| 격리 lifecycle | `.tmp/wave16-lifecycle/run-9w0usfic/evidence.json` install→HELLO→update→rollback→recovery | PASS (파일 실측). Codex 중간 실패 메시지보다 최종 증거가 앞섬 |
| Core version | vendor `0.1.2+iris.a382af23`, `legacy_migration_approved=false` | PASS |
| Gateway-free one-shot | headless `_oneshot_route` + GUI `_summary_route_for`→`resolve_title_route`. unittest 3 ok | DONE |
| IDE Bridge NIP-06 | bridge_nav FAIL→PASS(active editor push). 6 포커스 체크 + sync | 계약 DONE / GUI 수동 OPEN |
| Native tool NIP-05 | 계약 PASS + owned live shell `finished_exactly:true` (NIP-04) | DONE |

## 4. NIP 상태 (이번 재개 기준)

| Phase | 상태 | 비고 |
|---|---|---|
| NIP-00 Baseline | DONE | HEAD=`44df2f2` + wave16 audit 산출 |
| NIP-01 Engine Independence | PARTIAL | Hermes auto-fallback 제거. 전경로 감사 잔여 |
| NIP-02 Residual/Gateway | 제품 핫패스 DONE / 모듈 ISOLATE | empty→`:8642` 부활 제거. gateway 모듈·진단 ISOLATE. spawn 제품 호출자 0 |
| NIP-03 Runtime Hardening | 계약 DONE | ollama cleanup·stall·cancel·idle·sidecar landing 5체크 PASS. 워킹트리 dirty/미커밋 |
| NIP-04 Tool grounding | DONE | ShellAssistNudge 복구. evidence `finished_exactly:true` + marker 인용 (재검증) |
| NIP-05 Tool security | DONE | 계약 PASS + live shell grounding PASS |
| NIP-06 IDE | 계약 DONE / GUI OPEN | openFile→current 탭 동기화 수정. 포커스 6체크 PASS. 제품 GUI 수동 잔여 |
| NIP-07 Product features | DONE | fpr_product_gui + vibe_smoke 9/9 PASS (`ide_id:iris_ide`, Iris 재시작 후) |
| NIP-08 E2E infra | 러너 배선 DONE / flag 실실행 OPEN | L5=`_check_fpr_product_gui`+`--include-gui`. L6=`_check_owned_lifecycle`+`--include-lifecycle`. contracts-only 17/17 유지 |
| NIP-09 Model quality | PARTIAL | gpt-oss HELLO·lifecycle·finished_exactly·피커/빌링 PASS. 멀티툴/멀티모델·외부 live OPEN (`.tmp/nip09-w16-snapshot/STATUS.md`) |
| NIP-10 Lifecycle | PARTIAL/PASS 격리 | 격리 evidence PASS. 제품 홈 재설치는 KEEP 주의 |
| NIP-11 Hygiene | DONE | `.gitignore` 로그만 ignore·소스 keep. wave16 audit는 `.tmp/`. branding·no-console PASS |
| NIP-12 Full regression | OPEN | |
| NIP-13 Wave 2 Entry | KEEP | 공개 GO 금지. 개발은 계속 |

## 5. 재개 단위 (직렬/병렬)

| 단위 | 병렬 | 검증 |
|---|---|---|
| NIP-04 grounding | DONE | evidence `finished_exactly:true` |
| A/B one-shot Gateway | DONE | headless + GUI summary |
| C IDE recovery | 계약 DONE | bridge_nav 등 재검증 PASS. GUI writeFile/타일 수동 OPEN |
| 다음 | NIP-03/07/08… | 계약 가능 단위부터 |

차단: dirty ~71 files — 공유 파일 병렬 쓰기 금지. NIP-12/13 fan-out 금지.

## 6. KEEP

- `legacy_migration_approved=false`
- hermes 물리 삭제 금지
- 요청 없는 commit/push
- 사용자 데이터 영구 삭제 금지

## 7. 조치

1. 공개 `legacy_migration_approved`·Wave 2 착수·commit/push는 요청 전까지 하지 않는다.
2. 다음 가역 단위(원하면): FPR13 `--include-live` L3, `--include-gui` L5 재실측, NIP-09 멀티툴 로컬 매트릭스, NIP-12 회귀 묶음.
3. 워킹트리는 dirty — 저장/커밋은 사용자 요청 시.

## 8. Wave 2 Entry (NIP-13)

| 조건 | 상태 |
|---|---|
| 핵심 독립성 (NIP-01/02 핫패스) | 개발 GO에 충분 (모듈 ISOLATE 잔여) |
| 제품 안정·보안 계약 | 대부분 DONE |
| NIP-09 품질 매트릭스 | PARTIAL → **차단** |
| NIP-12 Full regression | OPEN → **차단** |
| 공개 Production | KEEP false |
