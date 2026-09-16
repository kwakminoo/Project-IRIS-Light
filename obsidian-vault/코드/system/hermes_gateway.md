# hermes_gateway

`iris/system/hermes_gateway.py`

Hermes gateway 감지 및 자동 기동.

## 주요 정의

- `def _windows_hermes_candidates`
- `def hermes_executable`
- `def is_hermes_gateway_running`
- `def _gateway_argv`
- `def _gateway_child_env`
- `def _windows_hidden_cmd`
- `def _popen_hidden`
- `def start_hermes_gateway`
- `def stop_hermes_gateway`
- `def _gateway_lock_path`
- `def _lock_pid_alive`
- `def _pid_exists`
- `def _clear_stale_gateway_lock`
- `def _gateway_process_pids`
- `def _windows_gateway_procs_alive`
- `def _force_kill_windows_gateway_procs`
- `def ensure_hermes_gateway_running`
- `def restart_hermes_gateway`
- `def verify_iris_mcp_tools`
- `def ensure_hermes_provider_config`

## 내부 의존성

- [[hermes_client]]
- [[hermes_credentials]]
