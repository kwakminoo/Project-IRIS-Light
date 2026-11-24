## Why
Boot showed “Iris Agent 연결 준비를 확인하지 못했습니다”. `ensure_ready` ImportErrored because `aba2b75` removed `IRIS_AGENT_CHECKOUT_NAME` / prefer logic and left the install entrypoint as `install_hermes_with_system_python`.

## What changed
- Restore `IRIS_AGENT_CHECKOUT_NAME` / `LEGACY_AGENT_CHECKOUT_NAME` and iris-agent-prefer `iris_agent_repo_dir`.
- Rename `install_hermes_with_system_python` → `install_iris_agent_with_system_python` (no shim).

## Scope
- `iris/infrastructure/agent_runtime.py`
- `iris/system/iris_agent_install.py`

## Blast Radius
- Engine install/readiness path only.

## Verification
- `python -m iris.system._check_iris_agent_repo_dir` → ok
- `shared_engine().ensure_ready()` → `EngineReady engine is ready` (no `cannot import name`)
