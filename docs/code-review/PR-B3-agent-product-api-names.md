# PR-B3 — product API: agent_* only

| 항목 | 내용 |
|---|---|
| 문서 번호 | PR-B3 |
| 작성일 | 2026-11-19 |
| 관련 | Iris absorbs Hermes / hermes_* → agent_* |
| 대상 | Settings·kwargs·resolve_*·Control HTTP |
| 목적 | 제품 코드가 Settings.hermes_* / hermes_* kwargs를 쓰지 않게 함 |

## 1. 결론

제품 경로는 `agent_enabled` / `agent_command` / `agent_base_url` / `agent_api_key` 와 `resolve_agent_api_key` 만 쓴다. Settings의 `hermes_*` 프로퍼티 별칭은 삭제했다. Control HTTP도 `agent_enabled`만 emit·reject한다 (`hermes_enabled` dual-key 잔여 없음).

## 2. 구조

```
Settings.agent_*  ──► backend_route / build_state / ollama_guard / UI
                 ──► Control settings.get  → agent_enabled only
                 ──► Control settings.set  → reject disable via agent_enabled=false
                                           → hermes_enabled in args: ignored no-op
resolve_agent_api_key  ← product + gateway callers
resolve_hermes_api_key = resolve_agent_api_key  ← credentials thin reexport only
```

## 3. 남은 별칭 / 왜 남겼는지

| 남는 것 | 이유 |
|---|---|
| `resolve_hermes_api_key` thin reexport | `iris_agent_credentials` 내부 별칭. 제품 호출은 `resolve_agent_api_key`만 참조 (스크레이프 게이트). |
| env `IRIS_HERMES_*` 읽기 | **제거됨.** `load_settings`는 `IRIS_AGENT_*`만 읽는다. HERMES 키는 무시(별칭 없음). |
| `agent_command` 기본값 `"hermes"` | PATH 조회 깨짐 방지 (이번 유닛 out of scope). |
| UI 표시 문자열 "Hermes …" | PR-C. |
| thin `hermes_*.py` shim | **삭제됨** (Unit7). inventory: `hermes_shims=0`. |
| gateway 함수명 `hermes_executable` 등 | out of scope. |

## 4. 삭제된 것

- `Settings.hermes_enabled/command/base_url/api_key` properties
- `LightSettingsSelection.hermes_*` properties
- product kwargs `hermes_enabled=` / `hermes_base_url=` 등 (`backend_route`, `build_state`, `note_after_provider_direct_ok`, `SetupProtocol` 필드)
- SetupProtocol dual hermes_* 생성자/헬퍼 kwargs

## 5. 검증

- `iris.system._check_agent_product_api_names` ok
- `iris.config._check_iris_agent_policy_settings` ok
- `iris.ui._check_hermes_required` ok
- `iris.engine._check_iris_agent_sidecar_only` ok
- `iris.system._check_no_product_gateway_ops` ok
- inventory freeze: hermes_modules=0, hermes_shims=0 (Unit7 shim 삭제 후)
- `iris.ui._check_chat_landing_contract` ok
- `iris.ui._check_sidecar_done_landing` ok

## 6. 조치

없음 (이 유닛 완료). Unit7 thin shim 삭제 완료. 다음: gateway/worker 공개 심볼 rename (Unit4+).
