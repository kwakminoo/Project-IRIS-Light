# PHASE 15 Developer Cutover Runbook

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE15-DEVCUT-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | FINAL EXECUTION AUTHORIZATION · phase14 Gate · Owned Core |
| 대상 | 개발자 `~/.iris-light/agent` 엔진 선택 |
| 목적 | 안전조건 충족 후 Owned를 개발 정본으로 전환하는 가역 절차 |

## 1. 결론

공개 migration 플래그를 먼저 올리지 않는다. Hermes live를 Reference 슬롯으로 보존한 뒤 Owned를 새로 설치·선택한다. 실패 시 selection을 이전 슬롯으로 되돌린다.

## 2. 사전 조건 체크리스트

| # | 조건 | 증거 위치 |
|---|---|---|
| 1 | Owned `0.1.1` 격리 설치·Import | `.tmp/owned-core-011/evidence.json` |
| 2 | 핵심 모델·도구 왕복 | FIG-03 / shell live 증거 |
| 3 | 권한·승인 경로 | Gate B negative PASS |
| 4 | 사용자 데이터 백업 | `~/.iris-light` 설정·DB 복사본 경로 |
| 5 | 격리 Rollback 성공 | `rollback_iris_agent` 측정 |
| 6 | Reference 복구 가능 | hermes-agent 디렉터리 보존 + selection previous |

## 3. 구조

```
~/.iris-light/agent/
  hermes-agent/          → Reference (복구). 삭제 금지
  iris-agent.slot-XXXX/  → Owned 신규 설치
  iris-engine-selection.json
    active: iris-agent.slot-XXXX
    previous: hermes-agent
```

설치 게이트 `replacing_reference && !legacy_migration_approved`를 피하려면, 활성 checkout이 Hermes(무 SOURCE_MANIFEST)인 상태로 `update=True` 교체를 강제하지 않는다. 대신 Owned 슬롯을 새로 만들고 selection만 전환한다.

## 4. 조치 (조건 충족 후)

1. 백업: `config.yaml`, `iris_light.db`, selection(없으면 생략), SOUL.md.
2. 격리 홈에서 동일 pin 설치·Import·Rollback을 재확인.
3. live home에 Owned slot materialize + activate (`install_iris_agent_with_system_python`가 게이트에 막히면 selection API로 슬롯만 지정하는 최소 경로 사용).
4. 제품 기본 엔진 경로가 Owned를 가리키는지 확인.
5. HELLO + shell 1회 왕복.
6. 실패 시 `previous`로 rollback. Hermes 디렉터리는 유지.

## 5. 하지 않는 일

- `legacy_migration_approved` 공개 승격 (전체 사용자)
- Hermes Reference 물리 삭제
- commit/push (요청 전)
- 공개 릴리스 선언
