# Unit 0 — iris_agent_gateway Keep | Delete

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-19 |
| 관련 | `docs/prompts/Iris-Agent-sidecar-setup-gateway-잔재-구현프롬프트.md` |
| 목적 | 제품 표면에서 :8642 lifecycle Keep XOR Delete 고정 |

## 1. 결론

**Delete** (제품 `:8642` lifecycle gut). rename-only 파도 없음.

한 줄: 제품 호출자는 이미 `ensure_iris_agent_runtime(start_gateway=False)` + runtime probe만 쓰고, `prune_orphan_gateway_procs` 제품 호출자는 0이며 트리 kill은 `iris_agent_install._kill_hermes_tree_holders`에 있다. Keep 조건(모듈 전용 killer 필수)이 성립하지 않는다.

참고 ([Unit0 gateway Keep/Delete](622ea9da-6af6-4e29-8a02-5173d4412c2c) 조사): CI `_check_gateway_setup_step`·install `stop_hermes_gateway`가 모듈에 남아 **파일 통째 삭제**는 당장 불가. 프롬프트 Delete는 그 이전·체크 대체를 Unit 2에 포함하므로 XOR는 여전히 **Delete(gut)**. Keep-but-defer-rename은 gut와 모순되어 채택하지 않음.

## 2. 근거 (측정)

| 사실 | 근거 |
|---|---|
| 제품 start/restart/ensure_*gateway 호출 0 | `_check_no_product_gateway_ops`; 호출은 `_check_*`만 |
| orphan prune 제품 호출 0 | `prune_orphan_gateway_procs` → NONE outside gateway 모듈 |
| 설치 트리 kill은 install에 있음 | `_kill_hermes_tree_holders` in `iris_agent_install.py` |
| setup는 이미 sidecar 문구 | `_step_agent_runtime` summary `Iris Agent sidecar ready` + `start_gateway=False` |
| workspace `.env` / `.env.example` | `:8642` 미시드 (측정) |
| 남는 공유 헬퍼 | `probe_hermes_runtime`, `ensure_agent_provider_config`, `verify_iris_mcp_tools`, failure detectors, `stop_hermes_gateway`(install/update) |

## 3. Unit 2에 넘기는 범위

- `:8642` start/restart/ensure/health lifecycle gut 또는 진단 stub로 축소
- 헬퍼는 `iris_agent_install` / `agent_runtime` 쪽으로 옮기거나 모듈에 남기되 lifecycle과 분리
- rename 파도 skip

## 3b. Unit 2 Delete 결과 (제품 진단 = sidecar-only)

제품 설치·setup·채팅 진단은 InternalSidecar 준비(venv import · home · provider · SpeakTools)만 본다. `start_hermes_gateway` / `ensure_hermes_gateway_running` / `restart_hermes_gateway` / `prune_orphan_gateway_procs`는 기동하지 않는 stub이다. `stop_hermes_gateway`는 install/update retire용으로만 남긴다. `probe_gateway_health` / `is_hermes_gateway_running`은 `IRIS_AGENT_BASE_URL`이 있을 때 읽기 전용으로만 쓰며, 빈 URL과 레거시 `IRIS_HERMES_BASE_URL=:8642`는 제품 채팅에서 빈 `agent_base_url`로 취급한다. rename-only 파도는 없다.

## 4. setup/gateway-only hermes_* 공개 심볼 (아직 rename 안 함)

| 심볼 | 파일 |
|---|---|
| `probe_hermes_runtime` | `iris_agent_gateway.py` |
| `hermes_runtime_report` | 동상 |
| `start_hermes_gateway` / `stop_hermes_gateway` / `ensure_hermes_gateway_running` / `restart_hermes_gateway` | 동상 |
| `is_hermes_gateway_running` / `is_hermes_*_failure` | 동상 |
| `check_hermes_update` / `hermes_update_argv` | `iris_agent_update.py` |
| `load_hermes_tool_choice` 계열 | `iris_agent_tool_choice.py` (툴 카탈로그 Out of scope — 라벨만 Unit 3) |
| setup `_install_hermes` / `_step_*hermes*` 내부명 | `setup_protocol.py` |

툴 카탈로그·familiar·Speak fold는 이 결정에 포함하지 않음.
