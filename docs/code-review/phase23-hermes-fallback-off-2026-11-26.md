# Phase 23: NORMAL 경로 hermes 자동 폴백 끄기

| 항목 | 내용 |
|---|---|
| 문서 번호 | phase23-hermes-fallback-off-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | Owned cutover 이후 `iris_agent_repo_dir` |
| 대상 | `iris/infrastructure/agent_runtime.py` |
| 목적 | selection 없을 때 owned slot을 hermes보다 우선. hermes는 복구만 |

## 1. 결론

NORMAL resolve는 selection → `iris-agent/` → newest owned slot → (없을 때만) hermes recovery → canonical.
기존 live selection(`iris-agent.slot-…` / previous=`hermes-agent`)은 건드리지 않았다.
`hermes_cli` probe dual-accept는 유지했다.

## 2. 확인한 사실

| 항목 | 값 |
|---|---|
| live selection | active=`iris-agent.slot-e38f3ea761714c36`, previous=`hermes-agent` (미변경) |
| `legacy_migration_approved` | 미변경 |
| hermes-agent 삭제 | 하지 않음 |

## 3. 구조

```
iris_agent_repo_dir(home)
  ├─ read_engine_selection → active? → return active
  ├─ iris-agent/ is_dir? → return canonical
  ├─ _newest_owned_slot (SOURCE_MANIFEST) → return newest slot
  ├─ hermes-agent/ is_dir? → return legacy  (ponytail: recovery only)
  └─ return canonical (may not exist → probe fail-closed)
```

이번 요청이 갈라지는 지점: selection 없을 때 hermes를 owned slot보다 먼저 고르던 분기.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 요청을 막지 못한 이유 / 조치 |
|---|---|---|
| `iris_agent_repo_dir` | selection 없으면 canonical 없으면 바로 hermes | owned slot을 건너뜀 → slot 우선 삽입 |
| `_newest_owned_slot` | 없음 | 신규. SOURCE_MANIFEST + mtime |
| selection / rollback | previous·active 유지 | 손대지 않음 (하지 않은 일) |
| probe `iris_agent_cli`/`hermes_cli` dual-accept | 둘 다 허용 | 불확실 → 유지 (하지 않은 일) |

## 5. 개선안

| 빈 자리 | 내용 |
|---|---|
| 없음 (이번 범위) | NORMAL 경로 silent hermes 우선만 제거. selection.previous rollback은 기존 유지 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| 찾지 못함 | — | 로컬 selection/slot 계약만 조정 |

## 7. Before / After

| 상태 (selection 없음) | Before | After |
|---|---|---|
| empty home | `iris-agent` (목표) | 동일 |
| hermes only | `hermes-agent` | `hermes-agent` (recovery, 주석) |
| iris-agent only | `iris-agent` | 동일 |
| iris-agent + hermes | `iris-agent` | 동일 |
| owned slot + hermes | **`hermes-agent`** | **owned slot** |
| 여러 owned slot | hermes if no iris-agent/ | newest SOURCE_MANIFEST mtime |
| selection.active | active | 동일 |

## 8. 조치

1. `iris_agent_repo_dir` 우선순위 변경 + `ponytail:` 주석
2. `_check_iris_agent_repo_dir` / phase4 / agent_runtime self-check assert 갱신
3. 검증: repo_dir · owned_install · live selection resolve
