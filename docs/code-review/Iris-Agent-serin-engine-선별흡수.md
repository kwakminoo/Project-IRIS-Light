# Iris Agent — serin 내부 엔진 선별 흡수

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-ENGINE-ABSORB |
| 작성일 | 2026-10-27 |
| 관련 | `origin/serin` `iris/engine`, Phase 1–4 소유권, Phase 5 Prove |
| 대상 | 사이드카 엔진 + 우리 소유권 레이어 합침 |
| 목적 | `:8642` 기본 경로를 Iris 소유 sidecar로 옮기되, native registry·pin·홈은 유지 |

## 1. 결론

가져온 것: `iris/engine/**`, engine 단위 테스트, `HermesChatWorker`의 `shared_engine` 분기, 설치 `home=`/`sha=`/`probe_gateway`, 종료 시 sidecar shutdown.  
유지한 것: Iris Agent 홈·pin·native tool registry·설정 Hermes 필드 제거·Phase 5 Prove standin.  
가져오지 않은 것: serin `.tmp`/`graphify` 산출물, 브라우저 전용 대량 diff(이미 main에 있는 것과 별개), 진짜 in-process `AIAgent` import.

EngineHome 기본 경로 = `iris_agent_home()` (제품 홈과 동일). pin = `vendor/iris-agent-runtime/PIN`.

## 2. 구조

```
말 턴
  └─ HermesChatWorker
         ├─ InternalSidecar → shared_engine().run_turn (기본)
         └─ ExternalGateway → HTTP :8642 (설정 플래그 시에만)

설치
  └─ install_into(EngineHome)
         └─ install_hermes_with_system_python(home=…, sha=PIN, probe_gateway=False)
```

## 3. 코드 리뷰

| 지점 | 이번 일 | 남긴 것 |
|---|---|---|
| `iris/engine` | serin 패키지 흡수 | UI import Hermes 금지 유지 |
| `hermes_workers` | serin 엔진 분기 + Prove standin 재부착 | speak native wire는 ChatWorker 내부에 있을 수 있음 — 회귀 자검 |
| `hermes_install` | EngineHome용 home/sha/probe | serin extras 전부는 미포팅 |
| `types._default_engine_home` | agent home과 통일 | 예전 `~/.iris-light/engine` 단독 경로 폐기 |

## 4. 개선안

1. iris-control sync를 EngineHome에 묶는 serin 후속 커밋 검토.
2. Phase 5 Merge 문서를 “사이드카 기본 = 완료에 가깝다”로 갱신; 같은 프로세스 in-process는 선택 유지.
3. `ENGINE_HERMES_SHA` 모듈 상수 캐시 대신 항상 `_engine_pin_sha()` 호출로 단일화(이미 install 경로).

## 5. 차용

| 이름 | 가져올 부분 | 안 가져오는 이유 |
|---|---|---|
| serin `iris/engine` | sidecar·types·tests | `.tmp` 아레나 산출물 |
| 우리 Phase 1–4 | 소유권 게이트 | — |
| 진짜 in-process | — | Prove 후 선택; serin도 기본 거절 |
