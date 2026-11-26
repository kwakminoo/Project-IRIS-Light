# PHASE 22 Developer Owned Core cutover (live)

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE22-DEVCUT-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | PHASE 15 runbook · PHASE 21 rollback · FINAL EXECUTION AUTHORIZATION |
| 대상 | live `~/.iris-light/agent` |
| 목적 | Hermes를 recovery previous로 두고 Owned Core 0.1.1을 개발자 active로 전환 |

## 1. 결론

`IRIS_DEV_OWNED_CUTOVER=1`로만 replacing_reference 게이트를 열어 live 홈에 Owned Core 0.1.1을 설치·선택했다. active는 `iris-agent.slot-e38f3ea761714c36`, previous는 `hermes-agent`. hermes 디렉터리는 유지. `legacy_migration_approved`는 false 유지. **install_ok = true**. 공개 migration 플래그는 올리지 않았다.

## 2. 실측 표

| 필드 | 값 | 상태 |
|---|---|---|
| backup | `.tmp/dev-cutover-backup-20261126-152122` (config.yaml, SOUL.md, iris_light.db) | measured |
| selection 백업 | 없음 (cutover 전 selection 파일 없음) | measured |
| active | `iris-agent.slot-e38f3ea761714c36` | measured |
| previous | `hermes-agent` | measured |
| hermes_dir_exists | true | measured |
| SOURCE_MANIFEST version | `0.1.1+iris.a382af23` | measured |
| import AIAgent | true (active venv) | measured |
| probe_engine_python | ok (`None`) | measured |
| legacy_migration_approved | false (vendor 미승격) | measured |
| evidence | `.tmp/dev-cutover/evidence.json` | measured |

## 3. 구조

```
install_iris_agent_with_system_python(update=True)
  → current=hermes-agent (no SOURCE_MANIFEST) → replacing_reference
  → default: gate block
  → IRIS_DEV_OWNED_CUTOVER=1 → gate pass (dev only)
  → materialize iris-agent.slot-* + uv sync + probe
  → selection {active: slot, previous: hermes-agent}
```

갈라짐: 일반 사용자는 env 없이 계속 gate. 개발자 cutover만 env로 통과.

## 4. 코드 리뷰

| 지점 | 이번 요청에서 한 일 | 막거나 통과한 이유 |
|---|---|---|
| `_dev_owned_cutover_allowed` | env `1`/`true`/`yes`만 허용 | 기본 off · 공개 플래그 미사용 |
| replacing_reference gate | env 허용 시에만 통과 | hermes 교체 기본 차단 유지 |
| `_check_iris_agent_owned_install` | env 없이 gate, env 있으면 allowed | 회귀 잠금 |
| `_activate_staged` | previous=hermes-agent 기록 | recovery 경로 보존 |

하지 않은 일: hermes 삭제, `legacy_migration_approved` 승격, commit/push, 공개 릴리스 선언.

## 5. 개선안

구조상 빈 자리 없음. 공개 제품 cutover는 별도 parity 후 `legacy_migration_approved` 경로만 쓴다.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| 찾지 못함 | — | env 한 줄이면 충분 |

## 7. 조치

1. 개발 세션에서 Owned active 사용.
2. 문제 시 `rollback_iris_agent(home)` 또는 selection을 hermes-agent로 복구. 백업 경로 위 표.
3. 공개 사용자 게이트는 그대로 둔다.
