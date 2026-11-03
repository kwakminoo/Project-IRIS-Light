# Iris Agent 런타임 기준선 (Phase 1)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-BASELINE-P1 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Hermes기반-구현경로.md` §1·§4 1단계, §9, §10.1, §11 |
| 대상 | fork vs vendor 선택, pin, soft-patch 흡수, 홈 단일 함수 |
| 목적 | Phase 1 완료 기준을 코드·라이선스와 맞춘다 |

## 1. 결론

Phase 1 기준선은 **GitHub fork가 아니라** `vendor/iris-agent-runtime` 이다.  
업스트림 전체 트리를 Iris 모노레포에 넣지 않는다. 제품이 소유하는 것은 **pin SHA + Iris soft-patch 흡수 계약**이다.

설치·업데이트는 Nous `hermes-agent`를 **그 pin만** checkout한다. `origin/main` 추격은 하지 않는다.

홈은 `iris_agent_home()` 하나다. `IRIS_AGENT_HOME` / `~/.iris-light/agent` (기존 `%LOCALAPPDATA%\hermes`는 Phase 4 이전 호환).

## 2. 선택 표

| 안 | 판단 |
|---|---|
| GitHub fork | 보류. Iris 소유 원격 포크 없음. CVE 공개 rebase가 필요해지면 같은 pin으로 포크를 연다. |
| 전체 vendor 트리 | Phase 1에서 거절. 레포 비대, 이득 적음. |
| `vendor/iris-agent-runtime` pin+overlay | **채택** |

Pin (초기): `a382af23f4c067d23463b5781958684c2cda82bc`

## 3. LICENSE 영향

| 절 | 변경 |
|---|---|
| §3.3 | `vendor/iris-agent-runtime/` 추가. pin·절차·MIT 고지 계약. Hermes 전체 소스 번들 아님. |
| §3.4 | Hermes를 “번들 안 함·floating”에서 “pin checkout + overlay, MIT 고지”로 수정. |
| NOTICE / THIRD_PARTY | “Hermes Agent by Nous Research (MIT)” 유지. |

## 4. soft-patch

| 패치 | Phase 1 |
|---|---|
| ollama options guard | install/update overlay로 흡수. gateway는 **verify만** (문자열 치환 없음). |
| stdio dead-check | pin 업스트림이 이미 고침 → verify. 깨진 패턴이면 install overlay에서만 흡수. |
| terminal/browser disable | 소스 치환 아님. `config.yaml` 정책은 sync/setup 유지 (2단계에서 재배치). |

## 5. §10.1 (Phase 1 후)

| 게이트 | 상태 |
|---|---|
| 툴 registry 포크 소유 | 부분 전진 (2.1) — `Iris-Agent-tool-registry-Phase2.1.md` |
| 설정 생성권 Iris | 열림 (2~3) |
| 대화 정본 하나 | 열림 (2·4) |
| supervisor 하나 | 열림 (3) |

## 6. 조치

1. `vendor/iris-agent-runtime/PIN`·`UPSTREAM`·README 유지.
2. `iris.infrastructure.agent_runtime` 이 홈·pin·overlay 진입점.
3. 검증: `python -m iris.system._check_iris_agent_runtime_phase1`
