# FreeLLMAPI식 모델 로스터 연동 구현

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-12-roster |
| 작성일 | 2026-11-12 |
| 관련 | FreeLLMAPI 패턴 차용, AI Hub /models, 피커 색·EOL |
| 대상 | Iris Light 커스텀 API 모델 목록·한도·정책·EOL |
| 목적 | 구현 결과와 검증 증거를 남긴다 |

## 1. 결론

`/models` 메타·가격·modality·EOL을 `model_roster` 도메인이 소유하고, `ApiProvider.model_meta`에 영속하며, 피커는 `display_tier`와 공식 description만 쓴다. 목록 행은 삭제하지 않고 retired/unavailable로만 표시한다. Self-check 7종이 전부 통과했다. 커밋·PR은 하지 않았다.

## 2. 확인한 사실

| 검증 | 결과 |
|---|---|
| `python -m iris.infrastructure._check_model_roster` | ok |
| `python -m iris.infrastructure._check_model_roster_persist` | ok |
| `python -m iris.ui.chat._check_model_picker_roster` | ok |
| `python -m iris.storage._check_brand_roster_sync` | ok |
| `python -m iris.storage.api_providers` | ok |
| `python -m iris.infrastructure.openai_compat_client` | ok |
| `python -m iris.ui.chat.model_picker_menu` | ok |

라이브 NVIDIA `/models` 재프로브는 이 세션에서 돌리지 않았다. 증거는 위 모듈 self-check다.

## 3. 구조

```
브랜드 GET /models
    → openai_compat_client (model_entries 보존)
    → parse_listing / sync_from_listing / display_tier   [model_roster]
    → sync_provider_listing → ApiProvider.model_meta     [api_providers]
    → providers_panel._sync_roster_after_probe
    → MainWindow._append_ok_api_models
    → ChatPanel.set_models / picker_tier_color / _api_blurb

채팅·검증 404/410/gone
    → retire_provider_on_http(410)
    → model_states=unavailable + retired persist
    → 피커 새로고침

Rate-limit 429
    → RouteCooldownBook (기존, 변경 없음)
```

이번 요청이 갈라지는 지점: `_model_ids`가 메타를 버리던 경로 → `list_model_entries` / `ProbeResult.model_entries`. 피커 색이 tool_support 중심이던 경로 → `display_tier`.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 예전에 막지 못한 이유 |
|---|---|---|
| `_model_ids` / `list_models` | raw entry 보존 API 추가 | id만 모아 가격·설명·modality 손실 |
| `ApiProvider` | `model_meta` + roster 어댑터 | 상태맵만 있고 listing 메타 없음 |
| `model_roster` | parse/tier/sync/retire 단일 소유 | 규칙이 UI·프로브에 흩어질 뻔함 |
| `picker_tier_color` | free/off_domain/paid/unknown | 도구 미확인=주황이 free/유료와 충돌 |
| `_append_ok_api_models` | roster 메타 주입 | `requires_subscription=False` 고정 |
| `_on_api_probe_done` | listing sync + 가격 1회 재조회 | merge-only, 사라진 모델 soft-retire 없음 |
| `_mark_api_model_unavailable_on_4xx` | 410 retire 영속 | unavailable만 기록, retired 플래그 없음 |

하지 않은 일: FreeLLMAPI 프록시 임베드, 서명 카탈로그 피드, PROVIDERS/MODELS 그룹 해체, RouteCooldownBook 교체, 커밋/PR.

## 5. 개선안

| 빈 자리 | 내용 |
|---|---|
| 라이브 프로브 증거 | Iris 실행 후 NVIDIA 등 실제 `/models`로 색·retired 육안 확인 |
| 부분 listing 실패 UX | entries 비면 sync skip. 사용자에게 "목록 동기화 생략" 한 줄 표시는 아직 없음 |
| ai_catalog modality | 여전히 chat 강제 가능. 카탈로그 fitness와 roster modality 정합은 후속 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| FreeLLMAPI | 410 retire 영속, 카탈로그 재읽기 mid-change, chat vs 비채팅 modality | Iris에 프록시·서명 피드를 넣지 않음 |
| 기존 Iris RouteCooldownBook | 429 cool-down | 이미 충분, 교체 불필요 |
| LiteLLM | (조사만) | 사용자가 FreeLLMAPI를 기준으로 지정 |

## 7. 설계 선택

| 후보 | 형태 | 판단 |
|---|---|---|
| A | `domain/model_roster` 패키지 | 규칙 소유에 유리. 베이스로 채택하되 파일을 한 모듈로 축소 |
| B | `ApiProvider.model_meta`만 확장 | 영속 형태를 graft로 채택 |

## 8. 조치

1. 소스만 반영됨. Iris 재시작 후 AI Hub 「테스트」로 브랜드 sync를 한 번 돌리면 피커 색·메타가 채워진다.
2. 커밋·PR이 필요하면 요청한다.
