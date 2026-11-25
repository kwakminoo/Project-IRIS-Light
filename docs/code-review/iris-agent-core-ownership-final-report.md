# IRIS Agent Core Ownership Final Report

| 항목 | 내용 |
|---|---|
| 문서 번호 | ACO-15 |
| 작성일 | 2026-11-25 |
| 관련 | Wave 1.2 Hotfix `d23f937` · PIN `a382af23` |
| 대상 | Agent Core 소유화 · 설치 · 레거시 격리 |
| 목적 | 최종 판정 GO / CONDITIONAL / NO-GO |

## 1. 결론

**판정: CONDITIONAL**

IRIS가 Agent Core 소스를 `vendor/iris-agent-core`로 소유하고, 기본 설치에서 Nous upstream clone을 제거했다. Reference Engine 실모델 턴·Product Preservation 자검은 PASS. 사용자 live는 Reference `hermes-agent`를 유지한 채 컷오버 코드를 적용했다(안전 롤백). 전체 제품 시나리오의 Owned 이중 라이브 벤치와 Gateway 물리 삭제는 후속.

Wave 2 착수: **가능(조건부)** — agent_turn 라이브는 증명됨. Memory/Skills 제품화는 Wave 2 범위.

## 2. A. 소스 관리

| 항목 | 값 |
|---|---|
| Upstream | https://github.com/NousResearch/hermes-agent.git |
| SHA | `a382af23f4c067d23463b5781958684c2cda82bc` |
| IRIS 관리 소스 | `vendor/iris-agent-core/` |
| 패키지 | `iris-agent-core` `0.1.0+iris.a382af23` |
| 라이선스 | MIT (Nous) — `LICENSE` + `PROVENANCE.md` + `THIRD_PARTY_NOTICES.md` |
| 변경 | overlay bake (ollama/tool_choice/identity/CLI/absorbed) |

## 3. B. Hermes Dependency Inventory

요약: [`iris-agent-core-hermes-inventory.md`](iris-agent-core-hermes-inventory.md)

| 유지 | 이전/대체 | 레거시 잔존 |
|---|---|---|
| AIAgent loop, providers, tool parse | install → owned materialize | `iris_agent_gateway.py` (start_gateway=False) |
| Sidecar SpeakTools | overlay → bake | hermes-mcp/skills (Wave2) |
| MIT/NOTICE | — | `vendor/iris-agent-runtime` pin 계약 |

## 4. C. 제품 기능 보존

| 기능 | 결과 |
|---|---|
| 모델 즐겨찾기/피커 | `_check_model_picker_roster` PASS; Hotfix HEAD 유지 |
| 실모델 요청·스트리밍·착지 | live_turn marker PASS (~7.5s) |
| Sidecar-only / no gateway spawn | PASS |
| Shell Box / 스크롤 / H1 | UI 미수정 |
| SpeakTools 단일 | PASS |

## 5. D. 엔진 동등성

| 지표 | Reference | Owned |
|---|---|---|
| 턴 성공 | PASS | 동일 소스 bake + materialize PASS |
| 실패율/크래시 | 0 (측정) | 계약 자검 PASS |
| 실행 시간 | 7.56–7.65s | (동일 루프; 이중 홈 설치 생략) |

상세: [`iris-agent-core-ownership-parity.md`](iris-agent-core-ownership-parity.md)

## 6. E. 설치·마이그레이션

| 항목 | 결과 |
|---|---|
| 기본 설치 | `_materialize_owned_core` — Nous clone 없음 |
| live 이름 | `iris-agent` |
| Reference 보존 | `hermes-agent` 미삭제 |
| Rollback | `iris-agent.prev-*` |
| Update | vendor sync 우선 |

자검: `python -m iris.system._check_iris_agent_owned_install`

## 7. F. 최종 판정

| 항목 | 상태 |
|---|---|
| Owned Core 소스 | 완료 |
| 공개 진입 `agent_entry` | 완료 |
| Hermes upstream 기본 설치 의존 제거 | 완료 |
| Agent Loop / Provider 보존 | 완료(Reference 라이브) |
| SpeakTools / Runtime / 승인 | 보존 |
| 사용자 데이터 | 미삭제 |
| Gateway 코드 삭제 | 미실시(격리·기본 OFF만) |
| Owned 이중 홈 풀 라이브 벤치 | 미실시 → CONDITIONAL |

**CONDITIONAL** — 코드 컷오버와 Reference 실증명은 충족. Owned를 사용자 기본 live로 강제 교체하거나 Gateway 삭제는 후속 hygiene.

## 8. 조치

1. `main` 커밋 + `origin/main` push (사용자 요청).  
2. 완료 문서를 검증 후 `docs/code-review/completed/`로 이동 가능.  
3. Wave 2는 Memory/Skills를 owned core 관측 지점 위에 구현.
