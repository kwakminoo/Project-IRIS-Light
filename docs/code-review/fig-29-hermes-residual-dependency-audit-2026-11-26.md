# FIG-29 Hermes Residual Dependency Audit

| 항목 | 내용 |
|---|---|
| 문서 번호 | FIG-29 |
| 작성일 | 2026-11-26 |
| 관련 | Wave 1 Final Integration · PHASE 06 |
| 대상 | Hermes/Owned Core 잔여 의존성 |
| 목적 | 물리 삭제 전 분류. 호출자 없으면 REMOVE, 아니면 KEEP/ISOLATE |

## 1. 결론

물리 **REMOVE** 후보 없음. Native Dispatcher가 제품 sidecar에서 Hermes 원본 `registry.dispatch` / `handle_function_call` 실행을 차단한다. Live 홈은 `hermes-agent` Reference만 존재한다. 삭제·이관 금지.

출처: 읽기 전용 감사 (explore agent). 이번 세션 파일 삭제 없음.

## 2. Native Dispatcher

| 지점 | 역할 |
|---|---|
| `_sidecar_main._install_iris_engine_tools` | `handle_function_call` → IRIS native dispatch |
| `_guard_hermes_registry_dispatch` | `registry.dispatch` → `TOOL_NOT_AVAILABLE` |
| `_check_native_tool_hermes_disabled` | 회귀 잠금 |

## 3. 분류

| 대상 | 분류 | 사유 |
|---|---|---|
| `vendor/.../tools/registry.py` | KEEP | 모듈 필요, dispatch만 가드 |
| `vendor/.../model_tools.py` | KEEP | facade + 런타임 치환 |
| `vendor/.../toolsets.py` | KEEP | toolset 사전 / overlay 대상 |
| `iris_agent_gateway.py` | ISOLATE | 기본 spawn 없음, 진단·opt-in |
| `iris_agent_control_sync.py` | KEEP | 설치·sync 축 |
| `iris_agent_absorbed_toolsets.py` | ISOLATE | baseline 미연결, 자검만 |
| `iris_agent_package_identity.py` | KEEP | 설치 overlay |
| `integrations/hermes-mcp` | ISOLATE | tombstone 템플릿 |
| `integrations/hermes-skills` | KEEP | skill 원본 |
| `integrations/hermes-plugins` | REFERENCE | iris importer 없음 |
| `integrations/hermes-soul` | KEEP | SOUL 원본 |
| `vendor/iris-agent-runtime` | KEEP | PIN 권위 |
| `~/.iris-light/agent/hermes-agent` | REFERENCE | live Reference. 삭제 금지 |

## 4. 조치

1. PHASE 06 물리 삭제 보류.
2. Cutover 전에도 홈 Reference 삭제 금지.
3. FIG-30+는 호출자 이전·검증 후만 검토.
