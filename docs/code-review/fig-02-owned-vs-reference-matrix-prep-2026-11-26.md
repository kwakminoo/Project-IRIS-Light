# FIG-02 Model/Engine Comparison Matrix — Prep

| 항목 | 내용 |
|---|---|
| 문서 번호 | FIG-02 |
| 작성일 | 2026-11-26 |
| 관련 | Wave 1 Final Integration · PHASE 01 |
| 목적 | 라이브 hermes 무변경으로 Owned/Reference 비교 경로 고정 |

## 1. 결론

격리 Owned fixture·설치 API는 이미 있다. 오늘 승인 없이 돌릴 최소 행렬은 Control + Native Dispatcher 자검(+기존 HELLO 증거)이다. 120B Owned 패리티는 유료 키·호출 승인 게이트.

## 2. Fixtures

| Fixture | 경로 | 재사용 |
|---|---|---|
| Owned HELLO | `.tmp/acf-clean/` (venv·manifest·probe-ok) | `turn-evidence.json` PASS |
| Reference HELLO | `.tmp/acf-ref-turn/` | 증거 PASS; 재실행 시 라이브 python 읽기만 |
| Product slots | `.tmp/acf-product/` | 격리 슬롯 전환 |
| Live agent | `~/.iris-light/agent` hermes only | **쓰기 금지** |

## 3. 설치 경로 (테스트 홈만)

- `install_iris_agent_with_system_python(home=…)`
- `Engine(InternalSidecar(EngineHome(tmp)))`
- selection은 해당 홈 상대 슬롯만

## 4. Blocked-on-approval

- 120B Cerebras/OpenRouter 유료 턴
- 라이브 cutover / selection 쓰기
- 유료 확대 행렬

## 5. Unit A (실행 · 2026-11-26)

| Check | 결과 |
|---|---|
| `_check_native_tool_hermes_disabled` | ok blocked=apply_patch,clarify,patch |
| `_check_native_tool_binding` | ok (FIG-04 TOOL_RESULT 포함) |
| `tests.test_iris_owned_core_release` | 8 OK |

## 6. 최소 비교 행렬 (오늘)

| Axis | Control/Contract | Owned (acf-clean 증거) | Reference (acf-ref 증거) |
|---|---|---|---|
| Native Dispatcher | PASS (Unit A) | — | — |
| HELLO 텍스트 턴 (`gpt-oss:20b`) | — | PASS `IRIS-ACF-HELLO` (7.5s) | PASS `IRIS-ACF-HELLO` (17.4s) |
| 120B / 유료 | — | 보류 (승인) | 보류 (승인) |

Owned python = `.tmp/acf-clean/iris-agent/venv/...`  
Reference python = live `hermes-agent/venv/...` (증거 재사용; 홈 미변경)
