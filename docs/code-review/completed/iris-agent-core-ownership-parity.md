# IRIS Agent Core Ownership Parity (ACO-12 / ACO-P7)

| 항목 | 내용 |
|---|---|
| 문서 번호 | ACO-12 |
| 작성일 | 2026-11-25 |
| 관련 | ACO-00 GO · owned install cutover |
| 대상 | Reference `hermes-agent` vs Owned `vendor/iris-agent-core` |
| 목적 | 컷오버 전 동등성·기본 경로 전환 판정 |

## 1. 결론

**판정: CONDITIONAL GO (컷오버 코드 완료, 라이브 제품은 Reference 유지)**

- Reference Engine 실모델 턴: PASS (marker echo ~7.5s, land_db_ok)
- Owned core materialize + 계약 자검: PASS
- 기본 설치 경로: Nous clone 제거 → `vendor/iris-agent-core` → live `iris-agent`
- 사용자 live 세션은 기존 `hermes-agent` Reference를 계속 사용(삭제·교체 없음). 신규/복구 설치만 owned 경로.

전체 시나리오 매트릭스(Shell 승인·IDE·Wiki 등)의 Reference↔Owned 이중 설치 병렬 벤치는 사용자 홈을 이중으로 깨지 않기 위해 **코드 컷오버 + Reference 라이브 + owned materialize**로 갈음. 허용 범위는 P0 기준선(≈7.6s marker)과 동일 모델을 사용.

## 2. 비교 조건

| 축 | 값 |
|---|---|
| Model | nvidia/nemotron-3-ultra-550b-a55b |
| Tool schema | Sidecar SpeakTools-only |
| Reference path | `~/.iris-light/agent/hermes-agent` |
| Owned source | `vendor/iris-agent-core` @ pin `a382af23` |

## 3. 결과

| 시나리오 | Reference | Owned | 비고 |
|---|---|---|---|
| probe / CLI import | PASS | materialize+stamp PASS | `_check_iris_agent_owned_install` |
| 일반 대화+착지 | PASS 7.56s | (동일 AIAgent 소스 bake) | live_turn.json |
| Sidecar-only | PASS | PASS | `_check_iris_agent_sidecar_only` |
| SpeakTools 단일 | PASS | bake+sidecar | `_check_speaktools_single_authority` |
| Gateway 비기본 | PASS | PASS | `_check_gateway_legacy_isolated` |
| 설치 경로 Nous 제거 | n/a | PASS | install source inspect |

증거: `.iris_light_test_tmp/verify-iris/aco-p7/`, `aco-p0/live_turn.json`

## 4. Cutover

| 항목 | 상태 |
|---|---|
| 기본 install = owned materialize | 적용 |
| live checkout 이름 `iris-agent` | 적용 |
| Reference `hermes-agent` 보존 | 적용 |
| UI 이중 엔진 선택 | 없음 |
| Rollback | `iris-agent.prev-*` + Reference 폴더 유지 |

## 5. 조치

1. 최종 보고서 ACO-P8 작성.  
2. 이후 신규 설치/복구는 owned core만 사용.  
3. Reference 제거는 장기 hygiene(호출자 0 확인 후).
