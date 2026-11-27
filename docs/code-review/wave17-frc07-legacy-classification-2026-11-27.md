# FRC-07 Legacy migrate/retire classification

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FRC07-LEGACY-CLASSIFICATION |
| 작성일 | 2026-11-27 |
| 관련 | FRC-07, FIG-29, FC 호환 이전, `_check_gateway_legacy_isolated` |
| 대상 | Hermes/Gateway/진단 잔여 핫패스 |
| 목적 | KEEP_DIAGNOSTIC / REPLACE_VERIFIED / SAFE_DELETE_CANDIDATE 고정. 검증된 1건만 퇴역 |

## 1. 결론

제품 핫패스에서 Gateway spawn은 이미 단리됐다. 물리 hermes 홈·`legacy_migration_approved`·Vendor Gateway 모듈은 이번 단위에서 건드리지 않았다.

분류 결과 SAFE_DELETE로 닫은 것은 `scripts/apply_env_to_hermes.ps1` 한 건이다. 호출자 0, 대체는 `.env.example` → `~/.iris-light/agent/.env` 와 `migrate_legacy_agent_home` 이다. `_check_gateway_legacy_isolated`가 부재를 잠근다.

그 외 FIG-29 잔여는 KEEP_DIAGNOSTIC 또는 REPLACE_VERIFIED(호출자·패키징 잔여)로 남긴다. Wave 2 NO-GO 유지.

## 2. 확인한 사실

| 사실 | 근거 |
|---|---|
| `ensure_iris_agent_runtime(start_gateway=False)` 기본 | `_check_gateway_legacy_isolated` |
| 제품 spawn/detect에 `ensure_iris_agent_gateway_running` 없음 | NIP-01/02 · `_check_product_ready_no_gateway` |
| `apply_env_to_hermes.ps1` Python importer 0 | 저장소 `rg` (docs·테스트 문자열만) |
| `.env.example`이 스크립트명을 안내하지 않음 | `tests/test_iris_agent_env_example` |
| FIG-29 REMOVE 후보 없음 (2026-11-26) | `fig-29-hermes-residual-dependency-audit-2026-11-26.md` |

## 3. 구조

```
product hot path
  ensure_iris_agent_runtime(start_gateway=False)
    └─ InternalSidecar / Owned Core
         └─ Native dispatch (Hermes registry.dispatch 가드)

diagnostic / opt-in (KEEP_DIAGNOSTIC)
  start_gateway=True → iris_agent_gateway ensure/probe
  setup/install/update diagnosis · main_window get_last_gateway_diagnosis

compat copy (KEEP_DIAGNOSTIC)
  migrate_legacy_agent_home  (%LOCALAPPDATA%\hermes → ~/.iris-light/agent)

retired this unit (SAFE_DELETE closed)
  scripts/apply_env_to_hermes.ps1  → deleted
    └─ lock: _check_gateway_legacy_isolated.check_apply_env_to_hermes_script_retired
```

이번 요청 갈림: 제품 FRC-01..06 표면이 아니라 **레거시 스크립트·진단 모듈 분류/퇴역**만.

## 4. 분류표

| 대상 | 분류 | 사유 |
|---|---|---|
| `iris/system/iris_agent_gateway.py` | KEEP_DIAGNOSTIC | 기본 spawn 없음. 진단·opt-in·install/update·자검 importer 잔존 |
| `vendor/.../gateway` | KEEP_DIAGNOSTIC | FC 호환 표. 대체 기능 검증 전 유지 |
| `ensure_iris_agent_gateway_running` opt-in | KEEP_DIAGNOSTIC | `start_gateway=True` 명시 경로만 |
| `iris_agent_absorbed_toolsets.py` | KEEP_DIAGNOSTIC | baseline 미연결. 자검·phase4 기대만 |
| `integrations/hermes-mcp` | KEEP_DIAGNOSTIC | tombstone 템플릿. sync/scrub 증거 |
| `integrations/hermes-skills` · `hermes-soul` | KEEP_DIAGNOSTIC | sync 원본. 제품 스킬/Identity |
| `vendor/.../tools/registry.py` 등 | KEEP_DIAGNOSTIC | Native 가드 대상. 모듈 필요 |
| `~/.iris-light/agent/hermes-agent` | KEEP_DIAGNOSTIC | live Reference. 물리 삭제 금지 |
| `scripts/iris_hermes_bench/**` | KEEP_DIAGNOSTIC | 오프라인 grader. 제품 import 없음 |
| `migrate_legacy_agent_home` | KEEP_DIAGNOSTIC | 구 홈 복사 호환. 활성 writer 아님 |
| `ExternalGateway` 제품 타입 | REPLACE_VERIFIED | 제품 경로에서 제거됨. sidecar-only 자검 |
| `integrations/hermes-plugins` | REPLACE_VERIFIED | 런타임 importer 없음(`iris_web`). API/배포 문서가 소스로 유지 → 패키징 감사 전 삭제 금지 |
| `iris_agent_cli_shim_overlay` | REPLACE_VERIFIED | rename 후 no-op에 가깝지만 baseline에 배선. bake 후 재검토 |
| Chat `_log` scroll/typography tests | REPLACE_VERIFIED | FRC-06 행렬. H1 자검으로 대체 중 |
| `scripts/apply_env_to_hermes.ps1` | SAFE_DELETE_CANDIDATE → **퇴역 완료** | 제품 미사용. `.env.example`+migrate가 대체. 이번 단위에서 삭제 |

## 5. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 레거시를 막지 못한/남은 이유 |
|---|---|---|
| `_check_gateway_legacy_isolated` | `start_gateway` 기본 False·sidecar-only·spawn 모듈 존재 확인 + **스크립트 부재 잠금** | Gateway 모듈·진단 UI import는 의도적 KEEP |
| `agent_runtime.ensure_iris_agent_runtime` | 제품 기본은 gateway 미기동 | `start_gateway=True` 진단 분기 유지 |
| `main_window` / setup diagnosis | `get_last_gateway_diagnosis` 등 | 복구 UX. 삭제 시 진단 공백 |
| `.env.example` + `test_iris_agent_env_example` | Hermes/스크립트명 안내 금지 | 스크립트 파일 자체는 테스트가 안 지움 → FRC-07에서 삭제 |
| `apply_absorbed_toolsets_overlay` | 분류만 | baseline 미호출. 삭제는 bake 결정 후 |

하지 않은 일: hermes 홈 물리 삭제, `legacy_migration_approved` 승격, hermes-plugins/gateway 모듈 삭제, FRC-01..06 제품 파일 수정, commit/push.

## 6. 이번 퇴역

| 항목 | 내용 |
|---|---|
| 삭제 | `scripts/apply_env_to_hermes.ps1` |
| 대체 (검증됨) | `.env.example` → `.iris-light/agent/.env`; 구 데이터는 `migrate_legacy_agent_home` |
| 잠금 | `python -m iris.system._check_gateway_legacy_isolated` |
| 선택하지 않은 후보 | `hermes-plugins`(문서 소스), `absorbed_toolsets`(자검), gateway(진단), shim(baseline 배선) |

## 7. 개선안

| 빈 자리 | 다음 단위 |
|---|---|
| hermes-plugins 패키징/문서 경로 | API·IA 참조 제거 후 SAFE_DELETE 재판정 |
| gateway 모듈 분리 | probe/진단만 남기고 spawn 격리 (P6) |
| absorbed_toolsets | baseline bake 또는 자검 기대 정리 |
| cli_shim | Owned bake 후 overlay 제거 |

## 8. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| FIG-29 분류 | KEEP/ISOLATE/REFERENCE 축 | FRC-07 라벨(KEEP_DIAGNOSTIC 등)로만 재매핑 |
| `_check_gateway_legacy_isolated` | 기존 ACO-P6 잠금 | 새 검사 프레임워크 불필요 |
| `_check_gateway_retired_product_surface` | 제품 surface 문자열 계약 | 스크립트 부재와 역할이 다름 |
| 찾지 못함 | LOCALAPPDATA hermes `.env` 병합 대체 GUI | 제품은 agent 홈 `.env`만 사용 |

## 9. 조치

1. FRC-07 트래커를 PARTIAL로 갱신하고 본 문서를 가리킨다.
2. `python -m iris.system._check_gateway_legacy_isolated` 통과를 증거로 둔다.
3. hermes 물리 삭제·migration 플래그·커밋은 요청 전까지 금지.
