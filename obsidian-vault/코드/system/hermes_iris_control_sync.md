# hermes_iris_control_sync

`iris/system/hermes_iris_control_sync.py`

Hermes에 Iris Control MCP + 스킬을 자동 설치·검증.

## 주요 정의

- `def project_root`
- `def hermes_home`
- `def hermes_config_path`
- `def hermes_skills_iris_control_dir`
- `def repo_skills_iris_control_dir`
- `def iris_state_dir`
- `def sync_state_path`
- `class SyncReport`
- `def _python_cmd`
- `def desired_mcp_block`
- `def desired_mobile_mcp_block`
- `def _mcp_equivalent`
- `def ensure_mcp_in_config`
- `def ensure_skills_installed`
- `def load_mcp_servers_config`
- `def _resolve_command`
- `def _probe_iris_control_http`
- `def probe_mcp_server`
- `def audit_all_mcp_servers`
- `def verify_install`
- `def sync_iris_control`
- `def _self_check`

## 내부 의존성

- [[android_emulator]]
- [[hermes_memory_nudge]]
