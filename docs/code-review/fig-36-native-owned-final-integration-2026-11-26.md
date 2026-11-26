# FIG-36 Native Owned 최종 통합 현황

| 항목 | 내용 |
|---|---|
| 문서 번호 | FIG-36-OWNED-INT-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | PHASE 16–22 · FIG-03 · PHASE00-RWT · ACF-15 |
| 대상 | Native Owned Core cutover 진행 상태 (개발 홈) |
| 목적 | 개발 cutover까지 실측을 고정하고, 공개 릴리스 NO-GO와 잔여 OPEN을 분리 |

## 1. 결론

**개발 홈 Owned Native 정본화는 완료다. 공개 릴리스는 여전히 NO-GO다.**  
live active=`iris-agent.slot-e38f3ea761714c36`, previous=`hermes-agent`. hermes는 삭제하지 않았고 `legacy_migration_approved`는 false다. 격리 0.1.1·Gate B·FPR13 `--include-live` 20/20(phase26)·rollback·FIG-03·E owned-우선·post-cutover HELLO까지 통과했다. 공개를 막는 잔여는 migration 승격·hermes 물리 삭제·요청 없는 배포(KEEP)다.

| 판정 | 범위 | 근거 |
|---|---|---|
| GO (개발) | 개발자 live 홈 Owned active · FPR13 20/20 | `.tmp/dev-cutover` · `.tmp/fpr13/results.json` |
| NO-GO (공개) | 전체 사용자 · 공개 배포 · migration 승격 | 플래그 false · hermes 복구 슬롯 유지 |

## 2. 확인한 사실 (세션 실측)

| 단위 | 결과 | 증거 |
|---|---|---|
| Owned 격리 0.1.1 | version_match·import_ok·blockers=[] | `.tmp/owned-core-011/evidence.json` |
| Gate B 계약 | COMPLETE | phase17 |
| FPR13 러너 계약 | 16 pass | phase18 |
| Dead Hermes `install.ps1` 경로 제거 | COMPLETE | phase19 |
| ShellAssistNudge | COMPLETE (계약) | phase20 |
| 격리 rollback | rollback_ok·live_untouched | `.tmp/owned-rollback-proof/evidence.json` · phase21 |
| FIG-03 hello+shell 패리티 | hello_match·shell_match true | `.tmp/fig-03/evidence.json` |
| Dev cutover | install_ok·active iris-agent slot·previous hermes | `.tmp/dev-cutover/evidence.json` · phase22 |
| Post-cutover HELLO 스모크 | hello_ok·Owned repo_dir·blockers=[] | `.tmp/post-cutover-smoke/evidence.json` · phase24 |
| 공개 migration | false 유지 | vendor · evidence |
| hermes 물리 삭제 | 하지 않음 | hermes_dir_exists true |

## 3. 구조

요청(개발 Owned 정본화)이 지나가는 경로.

```
vendor iris-agent-core 0.1.1
  → [격리] .tmp/owned-core-011 설치·probe          ✓
  → [계약] Gate B / FPR13 runner / ShellAssist     ✓
  → [패리티] FIG-03 Owned vs Reference hello+shell ✓
  → [롤백] 격리 slot A↔B rollback                  ✓
  → [갈라짐] IRIS_DEV_OWNED_CUTOVER=1
        ├─ 개발 live ~/.iris-light/agent → Owned active ✓
        └─ 공개 경로 (env 없음 / migration false) → 차단 유지
  → [E] selection 없을 때 owned slot > hermes          ✓ (phase23)
  → [스모크] live repo_dir Owned + HELLO               ✓ (phase24)
  → [미완] FPR13 live 4행 · 공개 migration
```

이번 세션 갈라짐: **개발 cutover + post-cutover HELLO 스모크 통과**. 공개 승격·물리 삭제는 구조상 아직 막혀 있다.

## 4. 코드 리뷰 요약

| 지점 | 이번 증상/목표에서 한 일 | 요청을 막지 못한 / 막은 이유 |
|---|---|---|
| 격리 install (phase16) | 0.1.1 slot·import·계약 4종 exit 0 | live 홈은 건드리지 않음 → cutover와 분리 |
| Gate B (phase17) | 미등록·Hermes 원본·confirm 거절 계약 | 라이브 TOOL_RESULT는 soft UNVERIFIED |
| FPR13 runner (phase18) | contracts-only 16 pass | `IRIS_FPR13_LIVE=1` 4행은 OPEN |
| install.ps1 제거 (phase19) | dead Hermes 설치 경로 삭제 | 제품 핫패스와 무관, 잔해만 제거 |
| ShellAssistNudge (phase20) | host post-tool hint 계약 | 라이브 마커 인용은 soft |
| rollback (phase21) | 격리 previous 복귀·live untouched | 공개 삭제 게이트와 무관 |
| FIG-03 | hello+shell 패리티 true | 도구 전수·GUI 동등은 범위 밖 |
| Dev cutover (phase22) | env 게이트로 live Owned 선택 | migration 플래그·공개 배포는 열지 않음 |
| E fallback (phase23) | owned slot > hermes when no selection | hermes는 selection.previous/rollback만 |
| Post-cutover smoke (phase24) | live `iris_agent_repo_dir` Owned + temp-home HELLO | headless Engine; GUI 클릭 아님 |

하지 않은 일: hermes 디렉터리 삭제, `legacy_migration_approved` 승격, commit/push, 공개 릴리스 GO 선언.

## 5. 개선안

구조에서 빈 자리만.

| 빈 자리 | 다음 단위 |
|---|---|
| 공개 migration | Product/Engine 게이트 + 별도 승인 후 플래그 |
| hermes 물리 삭제 | FIG-33 조건 + 별도 승인 |
| (선택) Cursor companion vibe_smoke | IDE bridge 10054 — Native Owned 증명과 분리 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| 찾지 못함 | — | 슬롯·selection·env 게이트로 충분. 외부 마이그레이션 프레임워크 불필요 |

## 7. 잔여 (공개 NO-GO · KEEP)

| 우선 | ID / 항목 | 상태 |
|---|---|---|
| — | R-13FPR-GUI | COMPLETE · phase26 `--include-live` 20/20 |
| — | cutover 후 스모크 | COMPLETE · phase24 |
| KEEP | R-MIGRATE-FALSE 공개 migration | KEEP false |
| KEEP | R-PHYS-DELETE hermes 삭제 | KEEP |
| KEEP | commit/push · 공개 배포 | 요청 전 금지 |

## 8. 조치

1. 개발 세션은 Owned active(`iris-agent.slot-e38f3ea761714c36`)를 정본으로 쓴다. 문제 시 previous=`hermes-agent`로 rollback.
2. 공개 릴리스·전체 사용자 migration·hermes 삭제는 하지 않는다.
3. FINAL EXEC 개발 범위 Exit: 수행 가능 필수 구현은 닫힘. 잔여는 정책 KEEP.
4. 트래커: `docs/code-review/phase00-residual-work-tracker-2026-11-26.md`.
